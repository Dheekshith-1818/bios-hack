from backend.recovery.canary import CanaryController
from backend.recovery.proof import ProofGenerator
from backend.schemas import (
    ActionProposal, RootCauseCandidate, CascadePrediction,
    PolicyDecision, SubscoreBreakdown
)

def make_test_proof():
    generator = ProofGenerator()
    proposal = ActionProposal(
        incidentId="inc-c1",
        actionType="reroute_canary",
        targetId="redis-replica-a",
        undoDescription="Revert traffic",
        priorRevisionConfig={}
    )
    candidate = RootCauseCandidate(
        serviceId="redis-replica-a",
        score=88.0,
        subscoreBreakdown=SubscoreBreakdown(),
        explanation="Cache failure"
    )
    decision = PolicyDecision(decision="ALLOW", reasons=["Approved"])
    cascade = CascadePrediction(startingNode="redis-replica-a")
    return generator.create_proof(
        incident_id="inc-c1",
        evidence_refs=["ref-1"],
        candidates=[candidate],
        graph_version=1,
        cascade=cascade,
        policy_decision=decision,
        proposal=proposal,
        baseline_metrics={"p95_latency_ms": 50.0, "error_rate": 0.001},
        guardrail_thresholds={"max_error_rate_increase": 0.01, "max_latency_increase_pct": 0.10}
    )

def test_canary_passes_when_healthy():
    controller = CanaryController()
    proof = make_test_proof()
    passed, obs, next_status = controller.evaluate_step(
        proof=proof,
        current_percent=10.0,
        windows_observed=3,
        control_metrics={"p95_latency_ms": 60.0, "error_rate": 0.002},
        treatment_metrics={"p95_latency_ms": 52.0, "error_rate": 0.001}
    )
    assert passed
    assert obs.guardrailPass
    assert next_status == "CANARY_PASSED"

def test_canary_fails_on_guardrail_regression():
    controller = CanaryController()
    proof = make_test_proof()
    # Treatment has high error rate
    passed, obs, next_status = controller.evaluate_step(
        proof=proof,
        current_percent=10.0,
        windows_observed=1,
        control_metrics={"p95_latency_ms": 60.0, "error_rate": 0.002},
        treatment_metrics={"p95_latency_ms": 450.0, "error_rate": 0.050}
    )
    assert not passed
    assert not obs.guardrailPass
    assert next_status == "CANARY_FAILED"

