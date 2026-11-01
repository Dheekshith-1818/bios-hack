from typing import List
from backend.schemas import RootCauseCandidate, CascadePrediction

class ExplanationsEngine:
    def generate_incident_summary(self, incident_id: str, candidates: List[RootCauseCandidate], cascade: CascadePrediction) -> str:
        if not candidates:
            return "Incident under observation. Telemetry data currently insufficient to isolate probable root cause."

        top = candidates[0]
        affected_nodes = list(cascade.predictedImpact.keys())
        affected_str = ", ".join(affected_nodes) if affected_nodes else "isolated to service"

        return (
            f"Evidence-ranked probable root cause is '{top.serviceId}' with heuristic ranking strength {top.score}/100. "
            f"Reverse-dependency cascade analysis predicts outbound propagation impacting [{affected_str}] "
            f"with overall propagation risk {cascade.overallPropagationRisk*100:.1f}%. "
            f"Key evidence: {'; '.join(top.supportingEvidenceRefs[:2])}."
        )

explanations_engine = ExplanationsEngine()

