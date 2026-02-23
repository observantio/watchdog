"""Disk-backed storage for BeCertain analyze jobs and results."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.observability.becertain_models import AnalyzeJobStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), ensure_ascii=True)
    os.replace(temp_path, path)


@dataclass
class AnalyzeJobRecord:
    job_id: str
    tenant_id: str
    requested_by: str
    status: AnalyzeJobStatus
    created_at: datetime
    payload: Dict[str, Any]
    request_fingerprint: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    summary_preview: Optional[str] = None
    result_path: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    task: Optional[asyncio.Task] = None


class BeCertainAnalyzeJobStoreService:
    def __init__(
        self,
        *,
        storage_path: str,
        max_retained_per_user: int,
        job_ttl_seconds: int,
        report_retention_days: int,
    ) -> None:
        self._storage_root = Path(storage_path).expanduser()
        self._jobs_dir = self._storage_root / "jobs"
        self._results_dir = self._storage_root / "results"
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._results_dir.mkdir(parents=True, exist_ok=True)

        self._max_retained_per_user = max(1, int(max_retained_per_user))
        self._job_ttl_seconds = max(60, int(job_ttl_seconds))
        self._report_retention_seconds = max(0, int(report_retention_days)) * 24 * 60 * 60
        self._lock = asyncio.Lock()
        self._jobs: Dict[str, AnalyzeJobRecord] = {}
        self._load_from_disk()

    def _job_file(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_id}.json"

    def _result_file(self, job_id: str) -> Path:
        return self._results_dir / f"{job_id}.json"

    def _serialize_job(self, job: AnalyzeJobRecord) -> Dict[str, Any]:
        return {
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "requested_by": job.requested_by,
            "status": job.status.value,
            "created_at": job.created_at.isoformat(),
            "payload": job.payload,
            "request_fingerprint": job.request_fingerprint,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "duration_ms": job.duration_ms,
            "error": job.error,
            "summary_preview": job.summary_preview,
            "result_path": job.result_path,
        }

    def _deserialize_job(self, payload: Dict[str, Any]) -> Optional[AnalyzeJobRecord]:
        job_id = str(payload.get("job_id") or "").strip()
        status_raw = str(payload.get("status") or "").strip()
        created_at = _parse_datetime(payload.get("created_at"))
        if not job_id or not status_raw or created_at is None:
            return None
        try:
            status_value = AnalyzeJobStatus(status_raw)
        except ValueError:
            return None

        record = AnalyzeJobRecord(
            job_id=job_id,
            tenant_id=str(payload.get("tenant_id") or ""),
            requested_by=str(payload.get("requested_by") or ""),
            status=status_value,
            created_at=created_at,
            payload=payload.get("payload") or {},
            request_fingerprint=str(payload.get("request_fingerprint") or ""),
            started_at=_parse_datetime(payload.get("started_at")),
            finished_at=_parse_datetime(payload.get("finished_at")),
            duration_ms=payload.get("duration_ms"),
            error=payload.get("error"),
            summary_preview=payload.get("summary_preview"),
            result_path=payload.get("result_path"),
        )

        if record.status in {AnalyzeJobStatus.QUEUED, AnalyzeJobStatus.RUNNING}:
            record.status = AnalyzeJobStatus.FAILED
            record.finished_at = _utcnow()
            record.error = "Interrupted due to process restart before completion"
            if record.started_at:
                record.duration_ms = int((record.finished_at - record.started_at).total_seconds() * 1000)
            else:
                record.duration_ms = int((record.finished_at - record.created_at).total_seconds() * 1000)

        if record.result_path and not Path(record.result_path).exists():
            record.result_path = None
        return record

    def _load_from_disk(self) -> None:
        for file_path in sorted(self._jobs_dir.glob("*.json")):
            try:
                with file_path.open("r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except Exception:
                continue
            record = self._deserialize_job(raw)
            if record is None:
                continue
            self._jobs[record.job_id] = record
            _atomic_write_json(self._job_file(record.job_id), self._serialize_job(record))
        self._cleanup_sync()

    def _cleanup_sync(self) -> None:
        now = _utcnow()
        remove_ids: List[str] = []
        job_cutoff = now - timedelta(seconds=self._job_ttl_seconds)
        for job_id, job in self._jobs.items():
            if job.finished_at and job.finished_at < job_cutoff:
                remove_ids.append(job_id)
                continue
            if (
                self._report_retention_seconds > 0
                and job.finished_at
                and job.status == AnalyzeJobStatus.COMPLETED
                and job.finished_at < now - timedelta(seconds=self._report_retention_seconds)
            ):
                if job.result_path and Path(job.result_path).exists():
                    try:
                        Path(job.result_path).unlink()
                    except OSError:
                        pass
                job.result_path = None
                _atomic_write_json(self._job_file(job.job_id), self._serialize_job(job))

        for job_id in remove_ids:
            job = self._jobs.pop(job_id, None)
            if job:
                self._delete_files(job)

    def _delete_files(self, job: AnalyzeJobRecord) -> None:
        try:
            self._job_file(job.job_id).unlink(missing_ok=True)
        except OSError:
            pass
        if job.result_path:
            try:
                Path(job.result_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _copy_job(self, job: AnalyzeJobRecord) -> AnalyzeJobRecord:
        return replace(
            job,
            payload=dict(job.payload),
            result=dict(job.result) if isinstance(job.result, dict) else job.result,
            task=job.task,
        )

    def _enforce_user_retention_sync(self, *, user_id: str, tenant_id: str) -> None:
        scoped = [
            job for job in self._jobs.values()
            if job.requested_by == user_id and job.tenant_id == tenant_id
        ]
        if len(scoped) <= self._max_retained_per_user:
            return
        scoped.sort(key=lambda item: item.created_at, reverse=True)
        for stale in scoped[self._max_retained_per_user:]:
            if stale.status in {AnalyzeJobStatus.QUEUED, AnalyzeJobStatus.RUNNING}:
                continue
            removed = self._jobs.pop(stale.job_id, None)
            if removed:
                self._delete_files(removed)

    async def create_job(self, record: AnalyzeJobRecord) -> AnalyzeJobRecord:
        async with self._lock:
            self._cleanup_sync()
            self._enforce_user_retention_sync(user_id=record.requested_by, tenant_id=record.tenant_id)
            self._jobs[record.job_id] = record
            _atomic_write_json(self._job_file(record.job_id), self._serialize_job(record))
            return self._copy_job(record)

    async def update_job(self, job: AnalyzeJobRecord) -> None:
        async with self._lock:
            if job.job_id not in self._jobs:
                return
            self._jobs[job.job_id] = job
            _atomic_write_json(self._job_file(job.job_id), self._serialize_job(job))
            self._cleanup_sync()

    async def get_job(self, job_id: str) -> Optional[AnalyzeJobRecord]:
        async with self._lock:
            self._cleanup_sync()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return self._copy_job(job)

    async def list_jobs(
        self,
        *,
        user_id: str,
        tenant_id: str,
        status_filter: Optional[AnalyzeJobStatus] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> tuple[List[AnalyzeJobRecord], Optional[str]]:
        async with self._lock:
            self._cleanup_sync()
            scoped = [
                self._copy_job(job)
                for job in self._jobs.values()
                if job.requested_by == user_id and job.tenant_id == tenant_id
            ]

        if status_filter:
            scoped = [job for job in scoped if job.status == status_filter]
        scoped.sort(key=lambda item: item.created_at, reverse=True)

        start = 0
        if cursor:
            try:
                start = max(0, int(cursor))
            except ValueError:
                start = 0
        page_size = max(1, min(100, int(limit)))
        page = scoped[start:start + page_size]
        next_cursor = str(start + page_size) if start + page_size < len(scoped) else None
        return page, next_cursor

    async def write_result(self, *, job_id: str, result: Dict[str, Any]) -> Optional[str]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            result_path = self._result_file(job_id)
            _atomic_write_json(result_path, result)
            job.result_path = str(result_path)
            _atomic_write_json(self._job_file(job_id), self._serialize_job(job))
            return job.result_path

    async def read_result(self, *, job_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            self._cleanup_sync()
            job = self._jobs.get(job_id)
            if not job or not job.result_path:
                return None
            result_path = Path(job.result_path)
            if not result_path.exists():
                job.result_path = None
                _atomic_write_json(self._job_file(job.job_id), self._serialize_job(job))
                return None
            with result_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
