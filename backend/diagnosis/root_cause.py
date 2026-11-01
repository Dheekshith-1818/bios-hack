import time
import numpy as np
from typing import List, Dict, Any, Optional
from backend.schemas import RootCauseCandidate, SubscoreBreakdown
from backend.telemetry.aggregate import telemetry_aggregator
from backend.graph.live_graph import live_graph

class RootCauseRanker:
    def rank_candidates(self, anomalous_services: List[str], onset_times: Dict[str, float]) -> List[RootCauseCandidate]:
        if not anomalous_services:
            return []

        candidates: List[RootCauseCandidate] = []
        g = live_graph.graph.g

        # Find earliest onset time among all anomalous services
        earliest_ts = min(onset_times.values()) if onset_times else time.time()
        max_onset_spread = max(1.0, max(onset_times.values()) - earliest_ts) if onset_times else 1.0

        for s_id in anomalous_services:
            supporting_evidence = []
            contradictory_evidence = []

            # 1. Temporal Precedence (0.25)
            # Earlier onset relative to other nodes scores higher
            onset = onset_times.get(s_id, earliest_ts)
            dt = max(0.0, onset - earliest_ts)
            temporal_score = max(0.0, 1.0 - (dt / max_onset_spread))
            if dt < 2.0:
                supporting_evidence.append(f"Onset within {dt:.1f}s of earliest cluster symptom")
            else:
                contradictory_evidence.append(f"Onset occurred {dt:.1f}s after primary cluster symptom")

            # 2. Anomaly Magnitude (0.20)
            summary = telemetry_aggregator.get_service_summary(s_id)
            err_rate = summary.get("error_rate", 0.0)
            p95_lat = summary.get("p95_latency_ms", 0.0)
            lat_norm = min(1.0, p95_lat / 800.0)
            err_norm = min(1.0, err_rate / 0.20)
            mag_score = max(lat_norm, err_norm)
            supporting_evidence.append(f"P95 latency: {p95_lat}ms, Error rate: {err_rate*100:.1f}%")

            # 3. Downstream Impact (0.20)
            # Candidate's callers (dependents) degraded after it
            callers = live_graph.graph.get_callers(s_id)
            affected_callers = [c for c in callers if c in anomalous_services]
            if callers:
                downstream_score = len(affected_callers) / len(callers)
                if affected_callers:
                    supporting_evidence.append(f"{len(affected_callers)}/{len(callers)} upstream callers degraded after this service ({', '.join(affected_callers)})")
            else:
                # Leaf node with no callers (unlikely root cause for wide outage)
                downstream_score = 0.3
                contradictory_evidence.append(f"Service {s_id} has no known upstream callers in topology")

            # 4. Trace Path Evidence (0.15)
            spans = telemetry_aggregator.get_recent_spans(s_id, limit=30)
            error_spans = [sp for sp in spans if sp.status == "ERROR"]
            slow_spans = [sp for sp in spans if sp.duration_ms > 200.0]
            trace_ratio = (len(error_spans) + len(slow_spans)) / max(1, len(spans))
            trace_score = min(1.0, trace_ratio * 1.5)
            if error_spans:
                supporting_evidence.append(f"Trace evidence: {len(error_spans)} failed spans, {len(slow_spans)} degraded spans")
            else:
                contradictory_evidence.append("No explicit error spans found in recent traces")

            # 5. Structured Log Evidence (0.10)
            logs = telemetry_aggregator.get_recent_logs(s_id, limit=30)
            crit_logs = [l for l in logs if l.severity in ("CRITICAL", "ERROR")]
            log_score = min(1.0, len(crit_logs) / 5.0)
            if crit_logs:
                supporting_evidence.append(f"Structured logs: {len(crit_logs)} ERROR/CRITICAL events (e.g. {crit_logs[0].eventType})")
            else:
                contradictory_evidence.append("No ERROR/CRITICAL structured log events recorded")

            # 6. Topology Explanation (0.10)
            # Services deeper in the dependency tree (callees) are more likely fundamental root causes than ingress
            callees = live_graph.graph.get_callees(s_id)
            anomalous_callees = [c for c in callees if c in anomalous_services]
            if anomalous_callees:
                # If its own dependencies are also broken, this node might just be an intermediary!
                topo_score = 0.2
                contradictory_evidence.append(f"Callee dependency {anomalous_callees[0]} also anomalous; possible intermediary")
            else:
                topo_score = 0.95
                supporting_evidence.append(f"Deepest anomalous node in call chain; no anomalous callees below it")

            # Weighted sum
            raw_score = (
                0.25 * temporal_score +
                0.20 * mag_score +
                0.20 * downstream_score +
                0.15 * trace_score +
                0.10 * log_score +
                0.10 * topo_score
            )
            score_100 = round(raw_score * 100.0, 1)

            breakdown = SubscoreBreakdown(
                temporal_precedence=round(temporal_score, 3),
                anomaly_magnitude=round(mag_score, 3),
                downstream_impact=round(downstream_score, 3),
                trace_path_evidence=round(trace_score, 3),
                structured_log_evidence=round(log_score, 3),
                topology_explanation=round(topo_score, 3)
            )

            explanation = (
                f"Candidate {s_id} exhibits rank score {score_100}/100. "
                f"Onset temporal weight {temporal_score:.2f}, magnitude {mag_score:.2f}, "
                f"downstream degradation {downstream_score:.2f}. "
                f"Primary indicator: {supporting_evidence[0] if supporting_evidence else 'correlated telemetry'}."
            )

            candidates.append(RootCauseCandidate(
                serviceId=s_id,
                score=score_100,
                subscoreBreakdown=breakdown,
                supportingEvidenceRefs=supporting_evidence,
                contradictoryEvidenceRefs=contradictory_evidence,
                explanation=explanation
            ))

        # Sort descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:3]

root_cause_ranker = RootCauseRanker()

