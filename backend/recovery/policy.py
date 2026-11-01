import time
from typing import Dict, Any, List
from backend.schemas import ActionProposal, PolicyDecision, RootCauseCandidate
from backend.config import settings

VALID_ACTIONS = {
    "reroute_canary",
    "rollback_release",
    "scale_up",
    "disable_feature_flag",
    "restart_replica",
    "NO_ACTION"
}

CRITICAL_SERVICES = {
    "payment-service",
    "identity-service"
}

NON_RESTARTABLE_SERVICES = {
    "postgres-db",
    "redis-cache"
}

class PolicyEngine:
    def __init__(self, policy_version: str = "1.0.0"):
        self.policy_version = policy_version
        self.active_remediations: Dict[str, str] = {} # target_id -> action_id

    def evaluate(
        self,
        proposal: ActionProposal,
        top_candidate: RootCauseCandidate,
        predicted_blast_radius: int,
        evidence_timestamp: float,
        is_human_approved: bool = False
    ) -> PolicyDecision:
        reasons: List[str] = []
        missing_prereqs: List[str] = []

        # Gate 1: Allowlisted action type
        if proposal.actionType not in VALID_ACTIONS:
            reasons.append(f"Action '{proposal.actionType}' is not in the allowlisted autonomous action set.")
            return PolicyDecision(decision="DENY", reasons=reasons, policyVersion=self.policy_version)

        # Gate 2: Prohibit blind restart on shared stateful services
        if proposal.actionType == "restart_replica" and proposal.targetId in NON_RESTARTABLE_SERVICES:
            reasons.append(f"Policy strictly denies restarting shared persistence node '{proposal.targetId}'.")
            return PolicyDecision(decision="DENY", reasons=reasons, policyVersion=self.policy_version)

        # Gate 3: Root cause ranking strength threshold
        if top_candidate.score < settings.RCA_CONFIDENCE_THRESHOLD:
            reasons.append(
                f"Candidate score {top_candidate.score}/100 is below the safety threshold of {settings.RCA_CONFIDENCE_THRESHOLD}/100."
            )

        # Gate 4: Evidence freshness TTL
        evidence_age = time.time() - evidence_timestamp
        if evidence_age > settings.EVIDENCE_TTL_SECONDS:
            reasons.append(f"Evidence is stale ({evidence_age:.1f}s old > limit of {settings.EVIDENCE_TTL_SECONDS}s).")

        # Gate 5: Reversibility & Rollback plan
        if proposal.reversibility != "FULLY_REVERSIBLE" or not proposal.undoDescription:
            reasons.append("Action is not certified as fully reversible with an explicit rollback procedure.")

        # Gate 6: Blast radius
        if predicted_blast_radius > settings.MAX_BLAST_RADIUS:
            reasons.append(
                f"Predicted blast radius ({predicted_blast_radius}) exceeds maximum allowable radius ({settings.MAX_BLAST_RADIUS})."
            )

        # Gate 7: Concurrency lock per target
        if proposal.targetId in self.active_remediations:
            existing_act = self.active_remediations[proposal.targetId]
            if existing_act != proposal.id:
                reasons.append(f"Target '{proposal.targetId}' already has active remediation {existing_act}.")

        # Gate 8: Critical services require human approval unless already granted
        requires_human = False
        if proposal.targetId in CRITICAL_SERVICES or proposal.actionType == "rollback_release":
            requires_human = True
            if not is_human_approved:
                missing_prereqs.append("human_sre_approval")
                reasons.append(f"Target '{proposal.targetId}' is a protected digital public infrastructure asset requiring explicit SRE authorization.")

        if reasons:
            if requires_human and not is_human_approved and len([r for r in reasons if "SRE authorization" not in r]) == 0:
                return PolicyDecision(
                    decision="HUMAN_APPROVAL_REQUIRED",
                    reasons=reasons,
                    policyVersion=self.policy_version,
                    missingPrerequisites=missing_prereqs
                )
            return PolicyDecision(
                decision="DENY",
                reasons=reasons,
                policyVersion=self.policy_version,
                missingPrerequisites=missing_prereqs
            )

        return PolicyDecision(
            decision="ALLOW",
            reasons=["All deterministic safety guardrails satisfied: RCA strength verified, blast radius bounded, rollback certified."],
            policyVersion=self.policy_version
        )

    def lock_target(self, target_id: str, action_id: str):
        self.active_remediations[target_id] = action_id

    def release_target(self, target_id: str):
        self.active_remediations.pop(target_id, None)

    def reset(self):
        self.active_remediations.clear()

policy_engine = PolicyEngine()

