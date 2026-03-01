"""
System Service for collecting CPU, memory, disk, and network metrics, and determining system stress status based on configurable thresholds.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import logging
import os
import psutil
from typing import Dict, Any

from services.system.helpers import (
    cpu_metrics,
    memory_metrics,
    disk_metrics,
    network_metrics,
    determine_stress_status,
)

logger = logging.getLogger(__name__)

class SystemService:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        try:
            self.process.cpu_percent(interval=None)
        except Exception as e:
            logger.warning(f"Unable to prime CPU percent: {e}")

    def get_cpu_metrics(self) -> Dict[str, Any]:
        return cpu_metrics(self.process)

    def get_memory_metrics(self) -> Dict[str, Any]:
        return memory_metrics(self.process)

    def get_disk_metrics(self) -> Dict[str, Any]:
        return disk_metrics(self.process)

    def get_network_metrics(self) -> Dict[str, Any]:
        return network_metrics(self.process)

    def determine_stress_status(self, cpu_percent: float, memory_percent: float, connections: int) -> Dict[str, Any]:
        return determine_stress_status(cpu_percent, memory_percent, connections)

    def get_all_metrics(self) -> Dict[str, Any]:
        cpu = self.get_cpu_metrics()
        memory = self.get_memory_metrics()
        io = self.get_disk_metrics()
        network = self.get_network_metrics()
        stress = self.determine_stress_status(
            cpu["utilization"],
            memory["utilization"],
            network["total_connections"],
        )

        return {
            "cpu": cpu,
            "memory": memory,
            "io": io,
            "network": network,
            "stress": stress,
        }
