"""Orchestrates BeCertain analyze jobs with disk-backed state and async workers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from config import config
from models.access.auth_models import TokenData
from models.observability.becertain_models import AnalyzeJobStatus, AnalyzeRequestPayload
from services.becertain_job_runner_service import BeCertainAnalyzeJobRunnerService
from services.becertain_job_store_service import AnalyzeJobRecord, BeCertainAnalyzeJobStoreService
from services.becertain_proxy_service import becertain_proxy_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BeCertainAnalyzeJobService:
    def __init__(
        self,
        *,
        storage_path: Optional[str] = None,
        max_concurrency: Optional[int] = None,
        max_retained_per_user: Optional[int] = None,
        job_ttl_seconds: Optional[int] = None,
        report_retention_days: Optional[int] = None,
    ) -> None:
        self._store = BeCertainAnalyzeJobStoreService(
            storage_path=storage_path or str(getattr(config, "BECERTAIN_ANALYZE_STORAGE_PATH", "./data/becertain_jobs")),
            max_retained_per_user=max_retained_per_user or int(getattr(config, "BECERTAIN_ANALYZE_MAX_RETAINED_PER_USER", 50)),
            job_ttl_seconds=job_ttl_seconds or int(getattr(config, "BECERTAIN_ANALYZE_JOB_TTL_SECONDS", 3600)),
            report_retention_days=report_retention_days if report_retention_days is not None else int(getattr(config, "BECERTAIN_ANALYZE_REPORT_RETENTION_DAYS", 7)),
        )
        self._runner = BeCertainAnalyzeJobRunnerService(
            max_concurrency=max_concurrency or int(getattr(config, "BECERTAIN_ANALYZE_MAX_CONCURRENCY", 2)),
        )

    @staticmethod
    def _fingerprint(payload: Dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _duration_ms(started_at: Optional[datetime], created_at: datetime, finished_at: datetime) -> int:
        anchor = started_at or created_at
        return int((finished_at - anchor).total_seconds() * 1000)

    async def create_job(
        self,
        *,
        current_user: TokenData,
        tenant_id: str,
        payload: AnalyzeRequestPayload,
    ) -> AnalyzeJobRecord:
        now = _utcnow()
        materialized_payload = payload.model_dump()
        materialized_payload["tenant_id"] = tenant_id
        record = AnalyzeJobRecord(
            job_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            requested_by=current_user.user_id,
            status=AnalyzeJobStatus.QUEUED,
            created_at=now,
            payload=materialized_payload,
            request_fingerprint=self._fingerprint(materialized_payload),
        )
        created = await self._store.create_job(record)
        created.task = self._runner.submit(
            job_id=created.job_id,
            run_fn=lambda: self._run_job(job_id=created.job_id, current_user=current_user),
        )

        becertain_proxy_service.write_audit(
            current_user=current_user,
            action="becertain.analyze_job.create",
            resource_id=created.job_id,
            details={
                "tenant_id": tenant_id,
                "requested_by": current_user.user_id,
                "request_fingerprint": created.request_fingerprint,
            },
        )
        return created

    async def _run_job(self, *, job_id: str, current_user: TokenData) -> None:
        record = await self._store.get_job(job_id)
        if not record:
            return

        record.status = AnalyzeJobStatus.RUNNING
        record.started_at = _utcnow()
        record.error = None
        await self._store.update_job(record)

        becertain_proxy_service.write_audit(
            current_user=current_user,
            action="becertain.analyze_job.start",
            resource_id=job_id,
            details={"tenant_id": record.tenant_id},
        )

        try:
            upstream = await becertain_proxy_service.request_json(
                method="POST",
                upstream_path="/api/v1/analyze",
                current_user=current_user,
                tenant_id=record.tenant_id,
                payload=record.payload,
                audit_action="becertain.analyze_job.proxy",
            )
            result = upstream if isinstance(upstream, dict) else {"result": upstream}
            finished = _utcnow()

            current = await self._store.get_job(job_id)
            if not current:
                return
            current.status = AnalyzeJobStatus.COMPLETED
            current.finished_at = finished
            current.duration_ms = self._duration_ms(current.started_at, current.created_at, finished)
            current.error = None
            current.summary_preview = str(result.get("summary", ""))[:280] or None
            current.result = result
            current.result_path = await self._store.write_result(job_id=job_id, result=result)
            await self._store.update_job(current)

            becertain_proxy_service.write_audit(
                current_user=current_user,
                action="becertain.analyze_job.complete",
                resource_id=job_id,
                details={"tenant_id": record.tenant_id},
            )
        except Exception as exc:  # noqa: BLE001
            finished = _utcnow()
            current = await self._store.get_job(job_id)
            if not current:
                return
            current.status = AnalyzeJobStatus.FAILED
            current.finished_at = finished
            current.duration_ms = self._duration_ms(current.started_at, current.created_at, finished)
            detail = getattr(exc, "detail", str(exc))
            current.error = str(detail)[:500]
            current.result = None
            await self._store.update_job(current)
            becertain_proxy_service.write_audit(
                current_user=current_user,
                action="becertain.analyze_job.fail",
                resource_id=job_id,
                details={"tenant_id": record.tenant_id, "error": type(exc).__name__},
            )

    async def list_jobs(
        self,
        *,
        user_id: str,
        tenant_id: str,
        status_filter: Optional[AnalyzeJobStatus] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> tuple[List[AnalyzeJobRecord], Optional[str]]:
        jobs, next_cursor = await self._store.list_jobs(
            user_id=user_id,
            tenant_id=tenant_id,
            status_filter=status_filter,
            limit=limit,
            cursor=cursor,
        )
        for job in jobs:
            job.task = self._runner.get_task(job.job_id)
        return jobs, next_cursor

    async def get_job(self, *, job_id: str, user_id: str, tenant_id: str) -> AnalyzeJobRecord:
        job = await self._store.get_job(job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RCA job not found")
        if job.requested_by != user_id or job.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for this RCA job")
        job.task = self._runner.get_task(job_id)
        return job

    async def get_job_result(self, *, job_id: str, user_id: str, tenant_id: str) -> Dict[str, Any]:
        job = await self.get_job(job_id=job_id, user_id=user_id, tenant_id=tenant_id)
        if job.status != AnalyzeJobStatus.COMPLETED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RCA job is not completed yet")
        if isinstance(job.result, dict):
            return job.result
        result = await self._store.read_result(job_id=job_id)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="RCA job result has expired based on retention policy",
            )
        return result


becertain_analyze_job_service = BeCertainAnalyzeJobService()
