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
from custom_types.json import JSONDict

from services.system.helpers import (
    cpu_metrics,
    memory_metrics,
    disk_metrics,
    network_metrics,
    determine_stress_status,
)

logger = logging.getLogger(__name__)


def _float_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0

class SystemService:
    def __init__(self) -> None:
        self.process = psutil.Process(os.getpid())
        try:
            self.process.cpu_percent(interval=None)
        except psutil.Error as e:
            logger.warning(f"Unable to prime CPU percent: {e}")

    def get_cpu_metrics(self) -> JSONDict:
        return cpu_metrics(self.process)

    def get_memory_metrics(self) -> JSONDict:
        return memory_metrics(self.process)

    def get_disk_metrics(self) -> JSONDict:
        return disk_metrics(self.process)

    def get_network_metrics(self) -> JSONDict:
        return network_metrics(self.process)

    def determine_stress_status(self, cpu_percent: float, memory_percent: float, connections: int) -> JSONDict:
        return determine_stress_status(cpu_percent, memory_percent, connections)

    def get_all_metrics(self) -> JSONDict:
        cpu = self.get_cpu_metrics()
        memory = self.get_memory_metrics()
        io = self.get_disk_metrics()
        network = self.get_network_metrics()
        stress = self.determine_stress_status(
            _float_value(cpu.get("utilization")),
            _float_value(memory.get("utilization")),
            _int_value(network.get("total_connections")),
        )

        return {
            "cpu": cpu,
            "memory": memory,
            "io": io,
            "network": network,
            "stress": stress,
        }
