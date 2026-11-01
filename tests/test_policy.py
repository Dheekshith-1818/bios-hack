import time
from backend.recovery.policy import PolicyEngine
from backend.schemas import ActionProposal, RootCauseCandidate, SubscoreBreakdown

def test_policy_allow_safe_canary():
    engine = PolicyEngine()
    proposal = ActionProposal(
        incidentId="inc-1",
        actionType="reroute_canary",
        targetId="redis-replica-a",
        undoDescription="Restore traffic to replica A",
        priorRevisionConfig={"allocation": 100}
    )
    candidate = RootCauseCandidate(
        serviceId="redis-replica-a",
        score=85.0,
        subscoreBreakdown=SubscoreBreakdown(),
        explanation="High confidence cache failure"
    )
    decision = engine.evaluate(
        proposal=proposal,
        top_candidate=candidate,
        predicted_blast_radius=2,
        evidence_timestamp=time.time(),
        is_human_approved=False
    )
    assert decision.decision == "ALLOW"

def test_policy_deny_blind_database_restart():
    engine = PolicyEngine()
    proposal = ActionProposal(
        incidentId="inc-2",
        actionType="restart_replica",
        targetId="postgres-db",
        undoDescription="None",
        priorRevisionConfig={}
    )
    candidate = RootCauseCandidate(
        serviceId="postgres-db",
        score=95.0,
        subscoreBreakdown=SubscoreBreakdown(),
        explanation="Database bottleneck"
    )
    decision = engine.evaluate(
        proposal=proposal,
        top_candidate=candidate,
        predicted_blast_radius=1,
        evidence_timestamp=time.time(),
        is_human_approved=False
    )
    assert decision.decision == "DENY"
    assert any("strictly denies restarting shared persistence" in r for r in decision.reasons)

def test_policy_requires_human_approval_for_payment_rollback():
    engine = PolicyEngine()
    proposal = ActionProposal(
        incidentId="inc-3",
        actionType="rollback_release",
        targetId="payment-service",
        undoDescription="Re-deploy v2",
        priorRevisionConfig={"revision": "v2"}
    )
    candidate = RootCauseCandidate(
        serviceId="payment-service",
        score=90.0,
        subscoreBreakdown=SubscoreBreakdown(),
        explanation="Payment regression"
    )
    decision = engine.evaluate(
        proposal=proposal,
        top_candidate=candidate,
        predicted_blast_radius=2,
        evidence_timestamp=time.time(),
        is_human_approved=False
    )
    assert decision.decision == "HUMAN_APPROVAL_REQUIRED"

    # With approval, should be ALLOW
    approved_decision = engine.evaluate(
        proposal=proposal,
        top_candidate=candidate,
        predicted_blast_radius=2,
        evidence_timestamp=time.time(),
        is_human_approved=True
    )
    assert approved_decision.decision == "ALLOW"

