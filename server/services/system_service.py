"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

System service for collecting BeObservant process metrics and health status.
"""


import logging
import os
import psutil
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SystemService:
    """Service to collect system metrics using psutil for the BeObservant process."""

    def __init__(self):
        """Initialize with current process."""
        self.process = psutil.Process(os.getpid())
        try:
            self.process.cpu_percent(interval=None)
        except Exception as e:
            logger.warning(f"Unable to prime CPU percent: {e}")

    @staticmethod
    def _fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload

    def get_cpu_metrics(self) -> Dict[str, Any]:
        """Get CPU utilization metrics for the BeObservant process."""
        try:
            cpu_percent = self.process.cpu_percent(interval=None)
            if cpu_percent == 0:
                cpu_percent = self.process.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count() or 1
            num_threads = self.process.num_threads()

            normalized = cpu_percent / cpu_count if cpu_count else cpu_percent
            normalized = min(normalized, 100)
            
            return {
                "utilization": round(normalized, 2),
                "raw_utilization": round(cpu_percent, 2),
                "count": cpu_count,
                "threads": num_threads,
                "frequency_mhz": None  
            }
        except Exception as e:
            logger.error(f"Error getting CPU metrics: {e}")
            return self._fallback({
                "utilization": 0,
                "raw_utilization": 0,
                "count": 0,
                "threads": 0,
                "frequency_mhz": None
            })

    def get_memory_metrics(self) -> Dict[str, Any]:
        """Get memory utilization metrics for the BeObservant process."""
        try:
            mem_info = self.process.memory_info()
            mem_percent = self.process.memory_percent()
            rss_mb = mem_info.rss / (1024 ** 2)
            vms_mb = mem_info.vms / (1024 ** 2)
            
            return {
                "rss_mb": round(rss_mb, 2),
                "vms_mb": round(vms_mb, 2),
                "utilization": round(mem_percent, 2)
            }
        except Exception as e:
            logger.error(f"Error getting memory metrics: {e}")
            return self._fallback({
                "rss_mb": 0,
                "vms_mb": 0,
                "utilization": 0
            })

    def get_disk_metrics(self) -> Dict[str, Any]:
        """Get I/O metrics for the BeObservant process."""
        try:
            io_counters = self.process.io_counters()
            
            return {
                "read_mb": round(io_counters.read_bytes / (1024 ** 2), 2),
                "write_mb": round(io_counters.write_bytes / (1024 ** 2), 2),
                "read_count": io_counters.read_count,
                "write_count": io_counters.write_count
            }
        except Exception as e:
            logger.error(f"Error getting I/O metrics: {e}")
            return self._fallback({
                "read_mb": 0,
                "write_mb": 0,
                "read_count": 0,
                "write_count": 0
            })

    def get_network_metrics(self) -> Dict[str, Any]:
        """Get network connection metrics for the BeObservant process."""
        try:
            connections = self.process.connections(kind='inet')
            
            # Count connections by status
            status_counts = {}
            for conn in connections:
                status = conn.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_connections": len(connections),
                "established": status_counts.get('ESTABLISHED', 0),
                "listen": status_counts.get('LISTEN', 0),
                "time_wait": status_counts.get('TIME_WAIT', 0),
                "close_wait": status_counts.get('CLOSE_WAIT', 0)
            }
        except Exception as e:
            logger.error(f"Error getting network metrics: {e}")
            return self._fallback({
                "total_connections": 0,
                "established": 0,
                "listen": 0,
                "time_wait": 0,
                "close_wait": 0
            })

    def determine_stress_status(self, cpu_percent: float, memory_percent: float, connections: int) -> Dict[str, Any]:
        """Determine if the BeObservant process is under stress."""
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
        
        return {
            "status": status,
            "message": message,
            "issues": issues
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all process metrics in one call."""
        cpu = self.get_cpu_metrics()
        memory = self.get_memory_metrics()
        io = self.get_disk_metrics()
        network = self.get_network_metrics()
        stress = self.determine_stress_status(
            cpu["utilization"],
            memory["utilization"],
            network["total_connections"]
        )
        
        return {
            "cpu": cpu,
            "memory": memory,
            "io": io,
            "network": network,
            "stress": stress
        }
