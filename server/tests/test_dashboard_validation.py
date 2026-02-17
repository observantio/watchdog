import pytest

from services.grafana.dashboard_ops import _dashboard_has_datasource
from fastapi import HTTPException


def test_dashboard_with_templating_is_valid():
    dash = {"templating": {"list": [{"type": "datasource", "current": {"value": "prom-1"}}]}}
    assert _dashboard_has_datasource(dash) is True


def test_dashboard_with_panel_datasource_is_valid():
    dash = {"panels": [{"datasource": "prom-1", "targets": [{"expr": "up"}]}]}
    assert _dashboard_has_datasource(dash) is True


def test_dashboard_with_target_datasource_is_valid():
    dash = {"panels": [{"targets": [{"expr": "up", "datasourceUid": "prom-1"}]}]}
    assert _dashboard_has_datasource(dash) is True


def test_dashboard_missing_datasource_is_invalid():
    dash = {"panels": [{"targets": [{"expr": "up"}]}]}
    assert _dashboard_has_datasource(dash) is False


def test_dashboard_with_non_expr_target_but_no_datasource_is_allowed():
    # targets that don't look like metric queries shouldn't force datasource
    dash = {"panels": [{"targets": [{"text": "some text"}]}]}
    assert _dashboard_has_datasource(dash) is False
