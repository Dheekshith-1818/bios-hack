import time
import json
import hashlib
import uuid
from typing import Dict, Any, List
from backend.schemas import (
    RemediationProof, ActionProposal, RootCauseCandidate,
    CascadePrediction, PolicyDecision
)

class ProofGenerator:
    def create_proof(
        self,
        incident_id: str,
        evidence_refs: List[str],
        candidates: List[RootCauseCandidate],
        graph_version: int,
        cascade: CascadePrediction,
        policy_decision: PolicyDecision,
        proposal: ActionProposal,
        baseline_metrics: Dict[str, float],
        guardrail_thresholds: Dict[str, float]
    ) -> RemediationProof:
        proof_id = str(uuid.uuid4())
        created_at = time.time()
        ttl = 180.0

        rollback_plan = {
            "procedure": proposal.undoDescription,
            "target": proposal.targetId,
            "previous_state": proposal.priorRevisionConfig,
            "timeout_seconds": 15.0
        }

        explanation = (
            f"Remediation Proof for Incident {incident_id[:8]}. Action '{proposal.actionType}' targeting "
            f"'{proposal.targetId}' permitted under policy v{policy_decision.policyVersion}. "
            f"Guardrails protect citizen-portal latency and global error rate with 10% canary isolation."
        )

        proof = RemediationProof(
            id=proof_id,
            incidentId=incident_id,
            evidenceRefs=evidence_refs,
            rootCauseCandidates=candidates,
            graphVersion=graph_version,
            cascadePrediction=cascade,
            policyVersion=policy_decision.policyVersion,
            policyDecision=policy_decision,
            permittedScope=f"civicguard-domain:{proposal.targetId}",
            actionProposal=proposal,
            guardrailThresholds=guardrail_thresholds,
            baselineMetrics=baseline_metrics,
            rollbackPlan=rollback_plan,
            ttlSeconds=ttl,
            createdAt=created_at,
            operator="civicguard-autonomous-agent",
            contentHash="",
            explanation=explanation
        )

        # Compute SHA-256 digest
        proof.contentHash = self.compute_hash(proof)
        return proof

    def compute_hash(self, proof: RemediationProof) -> str:
        data = {
            "id": proof.id,
            "incidentId": proof.incidentId,
            "targetId": proof.actionProposal.targetId,
            "actionType": proof.actionProposal.actionType,
            "graphVersion": proof.graphVersion,
            "policyDecision": proof.policyDecision.decision,
            "createdAt": round(proof.createdAt, 4),
            "guardrailThresholds": proof.guardrailThresholds,
            "rollbackPlan": proof.rollbackPlan
        }
        encoded = json.dumps(data, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def verify_proof(self, proof: RemediationProof) -> Dict[str, Any]:
        """
        Validates integrity digest and expiration before action execution.
        """
        now = time.time()
        if now - proof.createdAt > proof.ttlSeconds:
            return {"valid": False, "reason": "Proof has expired beyond TTL"}

        expected_hash = self.compute_hash(proof)
        if expected_hash != proof.contentHash:
            return {"valid": False, "reason": "Proof integrity digest mismatch; potential tampering detected"}

        if proof.policyDecision.decision != "ALLOW":
            return {"valid": False, "reason": f"Policy decision is {proof.policyDecision.decision}, not ALLOW"}

        return {"valid": True, "reason": "Proof is valid and certified safe for canary execution"}

proof_generator = ProofGenerator()

