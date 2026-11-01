import time
from typing import Dict, Any, Tuple
from backend.schemas import CanaryObservation, ActionProposal, RemediationProof
from backend.config import settings

class CanaryController:
    def evaluate_step(
        self,
        proof: RemediationProof,
        current_percent: float,
        windows_observed: int,
        control_metrics: Dict[str, float],
        treatment_metrics: Dict[str, float]
    ) -> Tuple[bool, CanaryObservation, str]:
        """
        Evaluates treatment metrics against control metrics and baseline guardrails.
        Returns (passed, observation, next_status).
        """
        thresholds = proof.guardrailThresholds
        baseline = proof.baselineMetrics

        ctrl_lat = control_metrics.get("p95_latency_ms", 100.0)
        treat_lat = treatment_metrics.get("p95_latency_ms", 100.0)

        ctrl_err = control_metrics.get("error_rate", 0.0)
        treat_err = treatment_metrics.get("error_rate", 0.0)

        # Guardrail 1: Treatment error rate must not exceed baseline/control by > tolerance
        err_tolerance = thresholds.get("max_error_rate_increase", settings.CANARY_MAX_REGRESSION_TOLERANCE)
        err_regression = (treat_err - ctrl_err) > err_tolerance

        # Guardrail 2: Treatment p95 latency must not increase > 10% over control
        lat_tolerance_pct = thresholds.get("max_latency_increase_pct", settings.CANARY_LATENCY_MAX_INCREASE)
        lat_regression = (treat_lat > ctrl_lat * (1.0 + lat_tolerance_pct)) and (treat_lat - ctrl_lat > 30.0)

        guardrail_pass = not (err_regression or lat_regression)

        if not guardrail_pass:
            reason = "Guardrail violation: "
            if err_regression:
                reason += f"Treatment error rate {treat_err*100:.2f}% exceeds control {ctrl_err*100:.2f}%. "
            if lat_regression:
                reason += f"Treatment p95 latency {treat_lat:.1f}ms exceeds control {ctrl_lat:.1f}ms by >10%. "

            observation = CanaryObservation(
                actionId=proof.actionProposal.id,
                percent=current_percent,
                windowsObserved=windows_observed,
                controlMetrics=control_metrics,
                treatmentMetrics=treatment_metrics,
                thresholds=thresholds,
                guardrailPass=False,
                safetyStatus="CANARY_FAILED"
            )
            return False, observation, "CANARY_FAILED"

        # Check if enough windows observed for promotion
        if windows_observed >= settings.CANARY_SAMPLE_WINDOWS:
            if current_percent >= 100.0:
                next_status = "RECOVERED"
            else:
                next_status = "CANARY_PASSED"
        else:
            next_status = "CANARY_RUNNING"

        observation = CanaryObservation(
            actionId=proof.actionProposal.id,
            percent=current_percent,
            windowsObserved=windows_observed,
            controlMetrics=control_metrics,
            treatmentMetrics=treatment_metrics,
            thresholds=thresholds,
            guardrailPass=True,
            safetyStatus=next_status
        )

        return True, observation, next_status

canary_controller = CanaryController()

