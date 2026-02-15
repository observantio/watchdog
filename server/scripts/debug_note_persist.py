"""Quick script to reproduce and verify incident note persistence.

Usage: python server/scripts/debug_note_persist.py

This will:
 - create a test incident (if not exists)
 - call storage_service.update_incident(...) to add a note
 - re-read the incident from DB and print notes
"""
from datetime import datetime, timezone
import uuid

from services.storage_db_service import DatabaseStorageService
from db_models import AlertIncident as AlertIncidentDB
from database import get_db_session
from models.alerting.incidents import AlertIncidentUpdateRequest


def ensure_incident(tenant_id: str, fingerprint: str, alert_name: str):
    with get_db_session() as db:
        inc = db.query(AlertIncidentDB).filter(AlertIncidentDB.tenant_id == tenant_id, AlertIncidentDB.fingerprint == fingerprint).first()
        if inc:
            return inc.id
        new_id = str(uuid.uuid4())
        inc = AlertIncidentDB(
            id=new_id,
            tenant_id=tenant_id,
            fingerprint=fingerprint,
            alert_name=alert_name,
            severity="warning",
            status="open",
            notes=[],
            labels={},
        )
        db.add(inc)
        db.flush()
        return new_id


if __name__ == '__main__':
    svc = DatabaseStorageService()
    tenant = 'default'
    user = 'system-test-user'
    fingerprint = 'debug-note-fingerprint-1'

    incident_id = ensure_incident(tenant, fingerprint, 'Debug Alert for Notes')
    print('Incident id:', incident_id)

    payload = AlertIncidentUpdateRequest(note='scripted test note')
    updated = svc.update_incident(incident_id, tenant, user, payload)
    print('Update result notes:', updated.notes if updated else None)

    # re-open session to verify DB-persisted
    with get_db_session() as db:
        inc = db.query(AlertIncidentDB).filter(AlertIncidentDB.id == incident_id, AlertIncidentDB.tenant_id == tenant).first()
        print('DB notes raw:', inc.notes)
        print('DB notes type:', type(inc.notes))
        for n in inc.notes:
            print(n)
