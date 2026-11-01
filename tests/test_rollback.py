from backend.recovery.rollback import RollbackEngine
from backend.recovery.policy import policy_engine
from backend.recovery.proof import ProofGenerator
from backend.schemas import (
    ActionProposal, RootCauseCandidate, CascadePrediction,
    PolicyDecision, SubscoreBreakdown
)

def test_rollback_execution_releases_target_lock():
    generator = ProofGenerator()
    proposal = ActionProposal(
        incidentId="inc-rb-1",
        actionType="reroute_canary",
        targetId="redis-replica-a",
        undoDescription="Restore 100% traffic to replica A",
        priorRevisionConfig={"traffic": "100% replica-a"}
    )
    candidate = RootCauseCandidate(
        serviceId="redis-replica-a",
        score=85.0,
        subscoreBreakdown=SubscoreBreakdown(),
        explanation="Test candidate"
    )
    proof = generator.create_proof(
        incident_id="inc-rb-1",
        evidence_refs=["ref-1"],
        candidates=[candidate],
        graph_version=1,
        cascade=CascadePrediction(startingNode="redis-replica-a"),
        policy_decision=PolicyDecision(decision="ALLOW"),
        proposal=proposal,
        baseline_metrics={},
        guardrail_thresholds={}
    )

    # Lock target in policy engine
    policy_engine.lock_target("redis-replica-a", proposal.id)
    assert "redis-replica-a" in policy_engine.active_remediations

    # Execute rollback
    engine = RollbackEngine()
    res = engine.execute_rollback(proof, "Canary guardrail violation")
    assert res["success"]
    assert res["target"] == "redis-replica-a"
    assert "Restore 100% traffic" in res["undo_executed"]

    # Target lock must be released!
    assert "redis-replica-a" not in policy_engine.active_remediations

