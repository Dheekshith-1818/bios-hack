from typing import Dict, Any, Optional, List
from backend.store import store
from backend.schemas import AuditEvent

class AuditService:
    def log_event(
        self,
        event_type: str,
        actor: str,
        incident_id: Optional[str] = None,
        action_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        return store.append_audit_event(
            event_type=event_type,
            actor=actor,
            incident_id=incident_id,
            action_id=action_id,
            payload=payload or {}
        )

    def verify_ledger(self) -> Dict[str, Any]:
        return store.verify_audit_chain()

    def get_events(self, limit: int = 100) -> List[AuditEvent]:
        return store.get_audit_events(limit=limit)

audit_service = AuditService()

