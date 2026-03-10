"""
Helpers for system metrics collection and stress status determination.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging

import psutil
from custom_types.json import JSONDict

logger = logging.getLogger(__name__)

def _fallback(payload: JSONDict) -> JSONDict:
    return payload


def cpu_metrics(proc: psutil.Process) -> JSONDict:
    try:
        cpu_percent = proc.cpu_percent(interval=None)
        if cpu_percent == 0:
            cpu_percent = proc.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count() or 1
        num_threads = proc.num_threads()

        normalized = cpu_percent / cpu_count if cpu_count else cpu_percent
        normalized = min(normalized, 100)

        return {
            "utilization": round(normalized, 2),
            "raw_utilization": round(cpu_percent, 2),
            "count": cpu_count,
            "threads": num_threads,
            "frequency_mhz": None,
        }
    except (psutil.Error, AttributeError, OSError, RuntimeError, ValueError) as exc:
        logger.error("Error getting CPU metrics: %s", exc)
        return _fallback({
            "utilization": 0,
            "raw_utilization": 0,
            "count": 0,
            "threads": 0,
            "frequency_mhz": None,
        })


def memory_metrics(proc: psutil.Process) -> JSONDict:
    try:
        mem_info = proc.memory_info()
        mem_percent = proc.memory_percent()
        rss_mb = mem_info.rss / (1024 ** 2)
        vms_mb = mem_info.vms / (1024 ** 2)

        return {
            "rss_mb": round(rss_mb, 2),
            "vms_mb": round(vms_mb, 2),
            "utilization": round(mem_percent, 2),
        }
    except (psutil.Error, AttributeError, OSError, RuntimeError, ValueError) as exc:
        logger.error("Error getting memory metrics: %s", exc)
        return _fallback({
            "rss_mb": 0,
            "vms_mb": 0,
            "utilization": 0,
        })


def disk_metrics(proc: psutil.Process) -> JSONDict:
    try:
        io_counters = proc.io_counters()

        return {
            "read_mb": round(io_counters.read_bytes / (1024 ** 2), 2),
            "write_mb": round(io_counters.write_bytes / (1024 ** 2), 2),
            "read_count": io_counters.read_count,
            "write_count": io_counters.write_count,
        }
    except (psutil.Error, AttributeError, OSError, RuntimeError, ValueError) as exc:
        logger.error("Error getting I/O metrics: %s", exc)
        return _fallback({
            "read_mb": 0,
            "write_mb": 0,
            "read_count": 0,
            "write_count": 0,
        })


def network_metrics(proc: psutil.Process) -> JSONDict:
    try:
        connections = proc.connections(kind="inet")
        status_counts: dict[str, int] = {}
        for conn in connections:
            status = conn.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_connections": len(connections),
            "established": status_counts.get("ESTABLISHED", 0),
            "listen": status_counts.get("LISTEN", 0),
            "time_wait": status_counts.get("TIME_WAIT", 0),
            "close_wait": status_counts.get("CLOSE_WAIT", 0),
        }
    except (psutil.Error, AttributeError, OSError, RuntimeError, ValueError) as exc:
        logger.error("Error getting network metrics: %s", exc)
        return _fallback({
            "total_connections": 0,
            "established": 0,
            "listen": 0,
            "time_wait": 0,
            "close_wait": 0,
        })


def determine_stress_status(cpu_percent: float, memory_percent: float, connections: int) -> JSONDict:
    HIGH_CPU_THRESHOLD = 50
    HIGH_MEMORY_THRESHOLD = 80
    HIGH_CONNECTIONS_THRESHOLD = 100

    MODERATE_CPU_THRESHOLD = 25
    MODERATE_MEMORY_THRESHOLD = 50
    MODERATE_CONNECTIONS_THRESHOLD = 50

    issues = []
    if cpu_percent >= HIGH_CPU_THRESHOLD:
        issues.append(f"High CPU usage ({cpu_percent}%)")
    elif cpu_percent >= MODERATE_CPU_THRESHOLD:
        issues.append(f"Moderate CPU usage ({cpu_percent}%)")

    if memory_percent >= HIGH_MEMORY_THRESHOLD:
        issues.append(f"High memory usage ({memory_percent}%)")
    elif memory_percent >= MODERATE_MEMORY_THRESHOLD:
        issues.append(f"Moderate memory usage ({memory_percent}%)")

    if connections >= HIGH_CONNECTIONS_THRESHOLD:
        issues.append(f"High connection count ({connections})")
    elif connections >= MODERATE_CONNECTIONS_THRESHOLD:
        issues.append(f"Moderate connection count ({connections})")

    if any("High" in issue for issue in issues):
        status = "stressed"
        message = "Process is under high stress"
    elif issues:
        status = "moderate"
        message = "Process is under moderate load"
    else:
        status = "healthy"
        message = "Process is operating normally"

    return {"status": status, "message": message, "issues": issues}
