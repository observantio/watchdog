from tests._env import ensure_test_env
ensure_test_env()

import pytest

from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate
from services.grafana.route_payloads import parse_dashboard_create_payload, parse_dashboard_update_payload


def test_parse_dashboard_create_payload_with_wrapper():
    payload = {"dashboard": {"title": "Wrapped"}, "folderId": 1, "overwrite": True}
    out = parse_dashboard_create_payload(payload)
    assert isinstance(out, DashboardCreate)
    assert out.dashboard.title == "Wrapped"
    assert out.folder_id == 1


def test_parse_dashboard_create_payload_with_raw_dashboard():
    payload = {"title": "Raw", "panels": []}
    out = parse_dashboard_create_payload(payload)
    assert isinstance(out, DashboardCreate)
    assert out.dashboard.title == "Raw"
    assert out.folder_id == 0


def test_parse_dashboard_create_payload_invalid():
    with pytest.raises(ValueError):
        parse_dashboard_create_payload("not-a-dict")


def test_parse_dashboard_update_payload_with_wrapper():
    payload = {"dashboard": {"title": "WrappedUpdate"}, "folderId": 2, "overwrite": False}
    out = parse_dashboard_update_payload(payload)
    assert isinstance(out, DashboardUpdate)
    assert out.dashboard.title == "WrappedUpdate"
    assert out.folder_id == 2
    assert out.overwrite is False


def test_parse_dashboard_update_payload_with_raw_dashboard_defaults_overwrite_true():
    payload = {"title": "RawUpdate"}
    out = parse_dashboard_update_payload(payload)
    assert isinstance(out, DashboardUpdate)
    assert out.dashboard.title == "RawUpdate"
    assert out.overwrite is True


def test_parse_dashboard_update_payload_invalid():
    with pytest.raises(ValueError):
        parse_dashboard_update_payload(None)
