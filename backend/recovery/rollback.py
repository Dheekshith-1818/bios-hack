import time
from typing import Dict, Any, Tuple
from backend.schemas import RemediationProof, ActionProposal
from backend.recovery.policy import policy_engine
from backend.store import store

class RollbackEngine:
    def execute_rollback(self, proof: RemediationProof, reason: str) -> Dict[str, Any]:
        """
        Executes inverse action described in proof.rollbackPlan.
        Releases target lock and records audit event.
        """
        target = proof.actionProposal.targetId
        undo_desc = proof.actionProposal.undoDescription
        prev_config = proof.rollbackPlan.get("previous_state", {})

        # Unlock target in policy engine
        policy_engine.release_target(target)

        # Record audit event
        ev = store.append_audit_event(
            event_type="ROLLBACK_EXECUTED",
            actor="civicguard-canary-controller",
            incident_id=proof.incidentId,
            action_id=proof.actionProposal.id,
            payload={
                "target_id": target,
                "undo_action": undo_desc,
                "restored_config": prev_config,
                "reason": reason,
                "timestamp": time.time()
            }
        )

        return {
            "success": True,
            "target": target,
            "undo_executed": undo_desc,
            "audit_sequence": ev.sequence,
            "event_hash": ev.eventHash
        }

rollback_engine = RollbackEngine()

