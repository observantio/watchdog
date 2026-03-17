"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import pytest

from services.system import helpers


class DummyProcess:
    def __init__(self):
        self._cpu_calls = 0

    def cpu_percent(self, interval=None):
        self._cpu_calls += 1
        return 0 if self._cpu_calls == 1 else 40

    def num_threads(self):
        return 8

    def memory_info(self):
        class MI:
            rss = 1024 * 1024
            vms = 2 * 1024 * 1024

        return MI()

    def memory_percent(self):
        return 10

    def io_counters(self):
        class IO:
            read_bytes = 1024 * 1024
            write_bytes = 2 * 1024 * 1024
            read_count = 1
            write_count = 2

        return IO()

    def connections(self, kind=None):
        class C:
            status = 'ESTABLISHED'

        return [C()]


def test_cpu_metrics_normalization(monkeypatch):
    proc = DummyProcess()
    monkeypatch.setattr(helpers.psutil, 'cpu_count', lambda: 4)
    metrics = helpers.cpu_metrics(proc)
    assert metrics['raw_utilization'] == 40
    assert metrics['utilization'] == 10
    assert metrics['threads'] == 8


def test_memory_metrics():
    proc = DummyProcess()
    m = helpers.memory_metrics(proc)
    assert m['rss_mb'] == pytest.approx(1.0, rel=1e-3)
    assert m['vms_mb'] == pytest.approx(2.0, rel=1e-3)
    assert m['utilization'] == 10


def test_disk_metrics():
    proc = DummyProcess()
    d = helpers.disk_metrics(proc)
    assert d['read_mb'] == pytest.approx(1.0, rel=1e-3)
    assert d['write_mb'] == pytest.approx(2.0, rel=1e-3)


def test_network_metrics():
    proc = DummyProcess()
    n = helpers.network_metrics(proc)
    assert n['total_connections'] == 1
    assert n['established'] == 1


def test_stress_status():
    s = helpers.determine_stress_status(cpu_percent=70, memory_percent=20, connections=10)
    assert s['status'] == 'stressed'
    assert any('High CPU usage' in issue for issue in s['issues'])
