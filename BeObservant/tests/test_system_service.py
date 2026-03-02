"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

import unittest
from unittest.mock import MagicMock, patch

from tests._env import ensure_test_env

ensure_test_env()

from services.system_service import SystemService


class SystemServiceTests(unittest.TestCase):
    @patch('services.system_service.psutil.Process')
    @patch('services.system_service.psutil.cpu_count', return_value=4)
    def test_get_cpu_metrics_normalizes_by_core_count(self, _cpu_count, process_cls):
        proc = MagicMock()
        proc.cpu_percent.side_effect = [0, 40]
        proc.num_threads.return_value = 8
        process_cls.return_value = proc

        service = SystemService()
        metrics = service.get_cpu_metrics()

        self.assertEqual(metrics['raw_utilization'], 40)
        self.assertEqual(metrics['utilization'], 10)
        self.assertEqual(metrics['threads'], 8)

    @patch('services.system_service.psutil.Process')
    def test_determine_stress_status_high_cpu(self, process_cls):
        process_cls.return_value = MagicMock()
        service = SystemService()
        result = service.determine_stress_status(cpu_percent=70, memory_percent=20, connections=10)
        self.assertEqual(result['status'], 'stressed')
        self.assertTrue(any('High CPU usage' in issue for issue in result['issues']))

    @patch('services.system_service.psutil.Process')
    def test_get_memory_metrics_fallback_on_exception(self, process_cls):
        proc = MagicMock()
        proc.memory_info.side_effect = RuntimeError('boom')
        process_cls.return_value = proc

        service = SystemService()
        metrics = service.get_memory_metrics()
        self.assertEqual(metrics, {'rss_mb': 0, 'vms_mb': 0, 'utilization': 0})


if __name__ == '__main__':
    unittest.main()
