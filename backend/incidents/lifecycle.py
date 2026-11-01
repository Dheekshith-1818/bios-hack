import time
import uuid
from typing import Dict, List, Optional, Any
from backend.schemas import (
    Incident, RootCauseCandidate, RemediationProof, ActionProposal,
    CanaryObservation, PolicyDecision
)
from backend.diagnosis.root_cause import root_cause_ranker
from backend.diagnosis.cascade import cascade_predictor
from backend.recovery.proposals import proposal_engine
from backend.recovery.policy import policy_engine
from backend.recovery.proof import proof_generator
from backend.recovery.canary import canary_controller
from backend.recovery.rollback import rollback_engine
from backend.recovery.executor import unified_executor
from backend.incidents.audit import audit_service
from backend.telemetry.aggregate import telemetry_aggregator
from backend.store import store

VALID_TRANSITIONS = {
    "OBSERVING": {"SUSPECTED", "SUPPRESSED", "CONFIRMED"},
    "SUSPECTED": {"CONFIRMED", "SUPPRESSED", "OBSERVING"},
    "CONFIRMED": {"DIAGNOSING"},
    "DIAGNOSING": {"PROPOSED"},
    "PROPOSED": {"POLICY_CHECKED", "POLICY_DENIED"},
    "POLICY_CHECKED": {"CANARY_RUNNING", "POLICY_DENIED"},
    "CANARY_RUNNING": {"CANARY_RUNNING", "CANARY_PASSED", "CANARY_FAILED", "ROLLING_BACK"},
    "CANARY_PASSED": {"PROMOTING", "RECOVERED"},
    "PROMOTING": {"CANARY_RUNNING", "RECOVERED", "CANARY_FAILED", "ROLLING_BACK"},
    "CANARY_FAILED": {"ROLLING_BACK"},
    "ROLLING_BACK": {"ROLLED_BACK", "ESCALATED"},
    "ROLLED_BACK": {"ESCALATED", "OBSERVING"},
    "SUPPRESSED": {"OBSERVING"},
    "POLICY_DENIED": {"ESCALATED", "OBSERVING"},
    "RECOVERED": {"OBSERVING"},
    "ESCALATED": {"OBSERVING"}
}

class IncidentLifecycleManager:
    def __init__(self):
        self.active_incidents: Dict[str, Incident] = {}
        self.incident_history: List[Incident] = []
        self._load_from_store()

    def _load_from_store(self):
        all_inc = store.get_all_incidents()
        for inc in all_inc:
            if inc.status not in ("RECOVERED", "SUPPRESSED", "ROLLED_BACK", "ESCALATED"):
                self.active_incidents[inc.id] = inc
            self.incident_history.append(inc)

    def transition(self, incident: Incident, target_status: str, reason: str = "") -> bool:
        current = incident.status
        allowed = VALID_TRANSITIONS.get(current, set())
        if target_status not in allowed:
            # Force transition if in error recovery
            if target_status not in ("ESCALATED", "ROLLING_BACK", "ROLLED_BACK"):
                return False

        incident.status = target_status
        now = time.time()
        if target_status == "CONFIRMED":
            incident.confirmedAt = now
        elif target_status == "PROPOSED":
            incident.identifiedAt = now
        elif target_status == "RECOVERED":
            incident.recoveredAt = now

        store.save_incident(incident)
        audit_service.log_event(
            event_type=f"INCIDENT_STATE_{target_status}",
            actor="civicguard-lifecycle-manager",
            incident_id=incident.id,
            action_id=incident.activeAction.id if incident.activeAction else None,
            payload={"previous_status": current, "new_status": target_status, "reason": reason}
        )
        return True

    def create_or_update_incident(self, anomalous_services: List[str], onset_times: Dict[str, float]) -> Optional[Incident]:
        if not anomalous_services:
            return None

        # Check if an existing active incident covers overlapping scope
        active = None
        for inc in self.active_incidents.values():
            if inc.status in ("CONFIRMED", "DIAGNOSING", "PROPOSED", "POLICY_CHECKED", "CANARY_RUNNING", "PROMOTING"):
                overlap = set(inc.scope).intersection(set(anomalous_services))
                if overlap:
                    active = inc
                    break

        now = time.time()
        if not active:
            inc_id = str(uuid.uuid4())
            active = Incident(
                id=inc_id,
                status="CONFIRMED",
                symptoms=[f"Multi-signal anomaly detected on {', '.join(anomalous_services)}"],
                startTs=min(onset_times.values()) if onset_times else now,
                detectedAt=now,
                confirmedAt=now,
                scope=list(anomalous_services),
                severity="HIGH" if ("payment-service" in anomalous_services or "citizen-portal" in anomalous_services) else "MEDIUM"
            )
            self.active_incidents[active.id] = active
            self.incident_history.append(active)
            store.save_incident(active)
            audit_service.log_event(
                event_type="INCIDENT_CONFIRMED",
                actor="civicguard-detector",
                incident_id=active.id,
                payload={"scope": active.scope, "symptoms": active.symptoms}
            )
        else:
            # Merge scope
            active.scope = list(set(active.scope).union(set(anomalous_services)))
            store.save_incident(active)

        return active

    def diagnose_and_propose(self, incident_id: str, onset_times: Dict[str, float]) -> Optional[RemediationProof]:
        incident = self.active_incidents.get(incident_id)
        if not incident:
            return None

        self.transition(incident, "DIAGNOSING", "Commencing root cause ranking and cascade analysis")

        # 1. RCA Ranking
        candidates = root_cause_ranker.rank_candidates(incident.scope, onset_times)
        incident.probableRootCauses = candidates
        if not candidates:
            return None

        top = candidates[0]
        # 2. Cascade Prediction
        cascade = cascade_predictor.predict_cascade(top.serviceId)

        # 3. Action Proposal
        proposal = proposal_engine.generate_proposal(incident.id, top)
        incident.activeAction = proposal
        self.transition(incident, "PROPOSED", f"Generated action proposal {proposal.actionType} for {proposal.targetId}")

        # 4. Policy Check
        policy_decision = policy_engine.evaluate(
            proposal=proposal,
            top_candidate=top,
            predicted_blast_radius=len(cascade.predictedImpact),
            evidence_timestamp=time.time(),
            is_human_approved=False
        )

        # 5. Baseline metrics and Guardrail thresholds
        baseline_metrics = {
            "p95_latency_ms": 120.0,
            "error_rate": 0.005,
            "payment_success_rate": 0.995
        }
        guardrail_thresholds = {
            "max_error_rate_increase": 0.01,
            "max_latency_increase_pct": 0.10,
            "min_payment_success_rate": 0.990
        }

        # 6. Generate Remediation Proof
        proof = proof_generator.create_proof(
            incident_id=incident.id,
            evidence_refs=top.supportingEvidenceRefs,
            candidates=candidates,
            graph_version=1,
            cascade=cascade,
            policy_decision=policy_decision,
            proposal=proposal,
            baseline_metrics=baseline_metrics,
            guardrail_thresholds=guardrail_thresholds
        )

        incident.currentProof = proof
        if policy_decision.decision == "ALLOW":
            self.transition(incident, "POLICY_CHECKED", "Policy approved action for bounded canary execution")
        else:
            self.transition(incident, "POLICY_DENIED", f"Policy decision: {policy_decision.decision} - {'; '.join(policy_decision.reasons)}")

        store.save_incident(incident)
        audit_service.log_event(
            event_type="REMEDIATION_PROOF_GENERATED",
            actor="civicguard-proof-generator",
            incident_id=incident.id,
            action_id=proposal.id,
            payload={
                "proof_hash": proof.contentHash,
                "policy_decision": policy_decision.decision,
                "reasons": policy_decision.reasons
            }
        )

        return proof

    def approve_action(self, incident_id: str, operator_id: str = "sre-operator") -> Dict[str, Any]:
        incident = self.active_incidents.get(incident_id)
        if not incident or not incident.currentProof:
            return {"success": False, "reason": "No active incident or valid proof found"}

        proof = incident.currentProof
        # Re-evaluate with is_human_approved = True
        top = proof.rootCauseCandidates[0]
        decision = policy_engine.evaluate(
            proposal=proof.actionProposal,
            top_candidate=top,
            predicted_blast_radius=len(proof.cascadePrediction.predictedImpact),
            evidence_timestamp=time.time(),
            is_human_approved=True
        )

        proof.policyDecision = decision
        proof.contentHash = proof_generator.compute_hash(proof)

        if decision.decision != "ALLOW":
            self.transition(incident, "POLICY_DENIED", f"Approval rejected by policy: {decision.reasons}")
            return {"success": False, "reasons": decision.reasons}

        # Lock target
        policy_engine.lock_target(proof.actionProposal.targetId, proof.actionProposal.id)

        # Transition to CANARY_RUNNING (10%)
        self.transition(incident, "CANARY_RUNNING", f"Manual approval granted by {operator_id}; starting 10% canary")

        # Apply 10% canary via unified executor
        res = unified_executor.apply_action(proof.actionProposal, 10.0)

        audit_service.log_event(
            event_type="CANARY_STARTED",
            actor=operator_id,
            incident_id=incident.id,
            action_id=proof.actionProposal.id,
            payload={"canary_percent": 10.0, "executor_result": res}
        )

        return {"success": True, "percent": 10.0, "proof_hash": proof.contentHash}

    def evaluate_canary(
        self,
        incident_id: str,
        current_percent: float,
        windows_observed: int,
        control_metrics: Dict[str, float],
        treatment_metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        incident = self.active_incidents.get(incident_id)
        if not incident or not incident.currentProof:
            return {"status": "NO_ACTIVE_INCIDENT"}

        proof = incident.currentProof
        passed, obs, next_status = canary_controller.evaluate_step(
            proof=proof,
            current_percent=current_percent,
            windows_observed=windows_observed,
            control_metrics=control_metrics,
            treatment_metrics=treatment_metrics
        )
        incident.canaryObservation = obs

        if not passed:
            # Automatic Rollback!
            self.transition(incident, "CANARY_FAILED", "Guardrail breach detected in treatment telemetry")
            self.transition(incident, "ROLLING_BACK", "Initiating automatic immediate rollback")

            # Revert action
            unified_executor.revert_action(proof.actionProposal)
            rb_res = rollback_engine.execute_rollback(proof, "Treatment guardrail regression")

            self.transition(incident, "ROLLED_BACK", "Rollback verified; traffic restored to pre-change baseline")
            return {"status": "ROLLED_BACK", "observation": obs.model_dump(), "rollback": rb_res}

        if next_status == "CANARY_PASSED":
            # Progressive promotion: 10% -> 25% -> 50% -> 100%
            next_pct = 25.0 if current_percent == 10.0 else (50.0 if current_percent == 25.0 else 100.0)
            self.transition(incident, "PROMOTING", f"Canary passed at {current_percent}%; promoting to {next_pct}%")
            unified_executor.apply_action(proof.actionProposal, next_pct)
            return {"status": "PROMOTING", "promoted_to_percent": next_pct, "observation": obs.model_dump()}

        elif next_status == "RECOVERED":
            self.transition(incident, "RECOVERED", "100% rollout verified healthy; incident fully recovered")
            policy_engine.release_target(proof.actionProposal.targetId)
            self.active_incidents.pop(incident.id, None)
            return {"status": "RECOVERED", "observation": obs.model_dump()}

        store.save_incident(incident)
        return {"status": next_status, "observation": obs.model_dump()}

    def trigger_rollback(self, incident_id: str, reason: str = "Operator requested rollback") -> Dict[str, Any]:
        incident = self.active_incidents.get(incident_id)
        if not incident or not incident.currentProof:
            return {"success": False, "reason": "No active incident or proof found"}

        self.transition(incident, "ROLLING_BACK", reason)
        unified_executor.revert_action(incident.currentProof.actionProposal)
        rb_res = rollback_engine.execute_rollback(incident.currentProof, reason)
        self.transition(incident, "ROLLED_BACK", "Rollback executed")
        return rb_res

    def reset(self):
        self.active_incidents.clear()
        self.incident_history.clear()
        store.clear()
        policy_engine.reset()

incident_lifecycle = IncidentLifecycleManager()

