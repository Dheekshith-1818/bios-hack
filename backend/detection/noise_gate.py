from typing import Dict, Any, List, Tuple
from collections import defaultdict
from backend.config import settings

class NoiseGate:
    def __init__(self, persistence_windows: int = 2):
        self.persistence_windows = persistence_windows
        # service_id -> consecutive window count of anomaly
        self.consecutive_anomaly_windows: Dict[str, int] = defaultdict(int)
        self.consecutive_clean_windows: Dict[str, int] = defaultdict(int)
        self.suppressed_events_log: List[Dict[str, Any]] = []

    def evaluate(
        self,
        service_id: str,
        z_scores: Dict[str, float],
        cusum_scores: Dict[str, float],
        has_trace_evidence: bool,
        has_log_evidence: bool,
        is_slo_breach: bool,
        sample_count: int
    ) -> Tuple[str, List[str]]:
        """
        Returns (decision, reasons) where decision is one of:
        - "CONFIRMED": sustained multi-signal incident or critical SLO breach
        - "SUSPECTED": single-window or single-signal anomaly
        - "SUPPRESSED": transient spike filtered by noise gate
        - "HEALTHY": normal operation
        - "INSUFFICIENT_TELEMETRY": not enough samples
        """
        if sample_count < 5:
            return "INSUFFICIENT_TELEMETRY", ["Insufficient telemetry samples to compute robust baseline"]

        # Check if any robust z-score or CUSUM indicates anomaly
        max_z = max(z_scores.values()) if z_scores else 0.0
        max_cusum = max(cusum_scores.values()) if cusum_scores else 0.0
        is_anomalous = (max_z >= settings.Z_SCORE_THRESHOLD) or (max_cusum >= settings.CUSUM_THRESHOLD) or is_slo_breach

        if not is_anomalous:
            self.consecutive_clean_windows[service_id] += 1
            if self.consecutive_clean_windows[service_id] >= settings.CLEAN_WINDOWS_HYSTERESIS:
                self.consecutive_anomaly_windows[service_id] = 0
            return "HEALTHY", []

        # It IS anomalous in this window!
        self.consecutive_clean_windows[service_id] = 0
        self.consecutive_anomaly_windows[service_id] += 1
        windows_count = self.consecutive_anomaly_windows[service_id]

        reasons = []

        # Protected SLO critical override
        if is_slo_breach:
            reasons.append(f"Critical user-facing SLO breach on {service_id}")
            return "CONFIRMED", reasons

        # Multi-signal evaluation
        signal_families = []
        if max_z >= settings.Z_SCORE_THRESHOLD:
            signal_families.append("metric_robust_z")
        if max_cusum >= settings.CUSUM_THRESHOLD:
            signal_families.append("metric_cusum")
        if has_trace_evidence:
            signal_families.append("trace_spans")
        if has_log_evidence:
            signal_families.append("structured_logs")

        # Combine metric signals into one family
        metric_family_present = ("metric_robust_z" in signal_families or "metric_cusum" in signal_families)
        independent_signals = 0
        if metric_family_present:
            independent_signals += 1
        if has_trace_evidence:
            independent_signals += 1
        if has_log_evidence:
            independent_signals += 1

        if windows_count >= self.persistence_windows and independent_signals >= 2:
            reasons.append(
                f"Sustained anomaly across {windows_count} windows with {independent_signals} independent signal families ({', '.join(signal_families)})"
            )
            return "CONFIRMED", reasons

        # Transient spike check: if only 1 window and lacking multi-signal agreement
        if windows_count < self.persistence_windows:
            suppression_reason = (
                f"Transient spike on {service_id}: window {windows_count}/{self.persistence_windows}, "
                f"independent signals {independent_signals}/2. Suppressed by noise gate."
            )
            self.suppressed_events_log.append({
                "service_id": service_id,
                "windows": windows_count,
                "independent_signals": independent_signals,
                "max_z": round(max_z, 2),
                "reason": suppression_reason
            })
            return "SUPPRESSED", [suppression_reason]

        return "SUSPECTED", [f"Anomaly persistence {windows_count} windows, waiting for corroborating signal"]

    def reset(self):
        self.consecutive_anomaly_windows.clear()
        self.consecutive_clean_windows.clear()
        self.suppressed_events_log.clear()

noise_gate = NoiseGate(persistence_windows=settings.CONSECUTIVE_ANOMALY_WINDOWS)

