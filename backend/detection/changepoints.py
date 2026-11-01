import time
from typing import Dict, List, Any, Optional, Tuple
from backend.telemetry.aggregate import telemetry_aggregator
from backend.detection.baselines import service_baselines
from backend.detection.noise_gate import noise_gate
from backend.graph.live_graph import live_graph
from backend.config import settings

class ChangePointDetector:
    def __init__(self):
        self.confirmed_anomalous_services: set[str] = set()

    def scan_window(self) -> Dict[str, Any]:
        """
        Executes one detection cycle over all aggregated telemetry.
        Returns a dictionary of results per service and incident clusters.
        """
        summaries = telemetry_aggregator.get_all_summaries()
        service_statuses = {}
        anomalies_detected = []
        suppressed_detected = []

        for s_id, summary in summaries.items():
            sample_count = summary.get("sample_count", 0)
            p95_lat = summary.get("p95_latency_ms", 0.0)
            err_rate = summary.get("error_rate", 0.0)
            cpu = summary.get("cpu_percent", 0.0)

            # Baselines
            b_lat = service_baselines.get_or_create(s_id, "p95_latency_ms")
            b_err = service_baselines.get_or_create(s_id, "error_rate")
            b_cpu = service_baselines.get_or_create(s_id, "cpu_percent")

            # Check if incident currently confirmed on this service
            is_confirmed = (s_id in self.confirmed_anomalous_services)
            if not is_confirmed:
                b_lat.update(p95_lat)
                b_err.update(err_rate)
                b_cpu.update(cpu)

            z_lat = b_lat.compute_robust_z(p95_lat)
            z_err = b_err.compute_robust_z(err_rate)
            z_cpu = b_cpu.compute_robust_z(cpu)

            z_scores = {"latency": z_lat, "error_rate": z_err, "cpu": z_cpu}
            cusum_scores = {"latency": b_lat.cusum_pos, "error_rate": b_err.cusum_pos, "cpu": b_cpu.cusum_pos}

            # Check trace evidence (any recent error or high latency spans)
            recent_spans = telemetry_aggregator.get_recent_spans(s_id, limit=20)
            has_trace_evidence = any(s.status == "ERROR" or s.duration_ms > 200.0 for s in recent_spans)

            # Check structured log evidence (any WARN, ERROR, or CRITICAL)
            recent_logs = telemetry_aggregator.get_recent_logs(s_id, limit=20)
            has_log_evidence = any(l.severity in ("WARN", "ERROR", "CRITICAL") for l in recent_logs)

            # Protected SLO breach check: citizen-portal
            is_slo_breach = False
            if s_id == "citizen-portal":
                if p95_lat > 500.0 or err_rate > 0.03:
                    is_slo_breach = True

            decision, reasons = noise_gate.evaluate(
                service_id=s_id,
                z_scores=z_scores,
                cusum_scores=cusum_scores,
                has_trace_evidence=has_trace_evidence,
                has_log_evidence=has_log_evidence,
                is_slo_breach=is_slo_breach,
                sample_count=sample_count
            )

            service_statuses[s_id] = {
                "decision": decision,
                "reasons": reasons,
                "z_scores": z_scores,
                "cusum_scores": cusum_scores,
                "summary": summary
            }

            # Update live graph node status
            if decision == "CONFIRMED":
                self.confirmed_anomalous_services.add(s_id)
                service_baselines.pause_service(s_id)
                live_graph.update_node_status(s_id, "ANOMALOUS", {"max_z": max(z_scores.values())})
                anomalies_detected.append(s_id)
            elif decision == "SUPPRESSED":
                live_graph.update_node_status(s_id, "OBSERVING")
                suppressed_detected.append(s_id)
            elif decision == "HEALTHY":
                if s_id in self.confirmed_anomalous_services:
                    self.confirmed_anomalous_services.remove(s_id)
                    service_baselines.resume_service(s_id)
                live_graph.update_node_status(s_id, "HEALTHY")

        return {
            "timestamp": time.time(),
            "service_statuses": service_statuses,
            "confirmed_services": list(self.confirmed_anomalous_services),
            "anomalies_detected": anomalies_detected,
            "suppressed_detected": suppressed_detected
        }

    def reset(self):
        self.confirmed_anomalous_services.clear()
        service_baselines.reset()
        noise_gate.reset()

changepoint_detector = ChangePointDetector()

