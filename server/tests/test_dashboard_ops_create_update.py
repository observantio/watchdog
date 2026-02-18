import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests._env import ensure_test_env
ensure_test_env()

from fastapi import HTTPException

from models.grafana.grafana_dashboard_models import DashboardCreate, DashboardUpdate
from services.grafana import dashboard_ops


class DashboardOpsCreateUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_dashboard_allows_empty_panels(self):
        service = SimpleNamespace(
            grafana_service=SimpleNamespace(
                create_dashboard=AsyncMock(return_value={"dashboard": {"title": "Empty Dashboard"}, "uid": "uid1", "id": 1}),
                search_dashboards=AsyncMock(return_value=[]),
            ),
            logger=SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None),
            _validate_group_visibility=lambda *a, **k: [],
        )

        class _DummyDB:
            def add(self, _):
                pass

            def commit(self):
                pass

            def rollback(self):
                pass

        db = _DummyDB()

        dashboard_create = DashboardCreate(dashboard={"title": "Empty Dashboard", "panels": []}, folderId=0, overwrite=False)

        # skip title-conflict DB check for unit test simplicity
        orig_has_conflict = dashboard_ops._has_accessible_title_conflict
        dashboard_ops._has_accessible_title_conflict = AsyncMock(return_value=False)
        try:
            res = await dashboard_ops.create_dashboard(service, db, dashboard_create, user_id="user1", tenant_id="t1", group_ids=[], visibility="private")
            self.assertIsNotNone(res)
            self.assertEqual(res.get("uid"), "uid1")
        finally:
            dashboard_ops._has_accessible_title_conflict = orig_has_conflict

    async def test_create_dashboard_rejects_missing_datasource(self):
        service = SimpleNamespace(
            grafana_service=SimpleNamespace(create_dashboard=AsyncMock(), search_dashboards=AsyncMock(return_value=[])),
            logger=SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None),
        )
        db = SimpleNamespace(add=lambda *a, **k: None, commit=lambda *a, **k: None, rollback=lambda *a, **k: None)

        dashboard_create = DashboardCreate(dashboard={"title": "Bad", "panels": [{"targets": [{"expr": "up"}]}]}, folderId=0, overwrite=False)

        # skip title-conflict DB check for unit test simplicity
        orig_has_conflict = dashboard_ops._has_accessible_title_conflict
        dashboard_ops._has_accessible_title_conflict = AsyncMock(return_value=False)
        try:
            with self.assertRaises(HTTPException):
                await dashboard_ops.create_dashboard(service, db, dashboard_create, user_id="user1", tenant_id="t1", group_ids=[], visibility="private")
        finally:
            dashboard_ops._has_accessible_title_conflict = orig_has_conflict

    async def test_update_dashboard_rejects_missing_datasource(self):
        service = SimpleNamespace(
            grafana_service=SimpleNamespace(update_dashboard=AsyncMock(return_value={"dashboard": {"title": "Updated"}}), search_dashboards=AsyncMock(return_value=[])),
            logger=SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None),
        )
        db = SimpleNamespace(add=lambda *a, **k: None, commit=lambda *a, **k: None)

        dashboard_update = DashboardUpdate(dashboard={"title": "BadUpdate", "panels": [{"targets": [{"expr": "up"}]}]}, overwrite=True)

        # patch access check to bypass DB lookup
        orig_check = dashboard_ops.check_dashboard_access
        dashboard_ops.check_dashboard_access = lambda *a, **k: SimpleNamespace(created_by="user1", visibility="private", shared_groups=[])

        # skip title-conflict DB check for unit test simplicity
        orig_has_conflict = dashboard_ops._has_accessible_title_conflict
        dashboard_ops._has_accessible_title_conflict = AsyncMock(return_value=False)
        try:
            with self.assertRaises(HTTPException):
                await dashboard_ops.update_dashboard(service, db, "uid", dashboard_update, user_id="user1", tenant_id="t1", group_ids=[])
        finally:
            dashboard_ops.check_dashboard_access = orig_check
            dashboard_ops._has_accessible_title_conflict = orig_has_conflict

    async def test_update_dashboard_allows_empty_panels(self):
        service = SimpleNamespace(
            grafana_service=SimpleNamespace(update_dashboard=AsyncMock(return_value={"dashboard": {"title": "EmptyUpdated"}}), search_dashboards=AsyncMock(return_value=[])),
            logger=SimpleNamespace(debug=lambda *a, **k: None, error=lambda *a, **k: None),
        )
        db = SimpleNamespace(add=lambda *a, **k: None, commit=lambda *a, **k: None)

        dashboard_update = DashboardUpdate(dashboard={"title": "EmptyUpdated", "panels": []}, overwrite=True)

        orig_check = dashboard_ops.check_dashboard_access
        dashboard_ops.check_dashboard_access = lambda *a, **k: SimpleNamespace(created_by="user1", visibility="private", shared_groups=[])

        # skip title-conflict DB check for unit test simplicity
        orig_has_conflict = dashboard_ops._has_accessible_title_conflict
        dashboard_ops._has_accessible_title_conflict = AsyncMock(return_value=False)
        try:
            res = await dashboard_ops.update_dashboard(service, db, "uid", dashboard_update, user_id="user1", tenant_id="t1", group_ids=[])
            self.assertIsNotNone(res)
            self.assertEqual(res.get("dashboard", {}).get("title"), "EmptyUpdated")
        finally:
            dashboard_ops.check_dashboard_access = orig_check
            dashboard_ops._has_accessible_title_conflict = orig_has_conflict


if __name__ == '__main__':
    unittest.main()
