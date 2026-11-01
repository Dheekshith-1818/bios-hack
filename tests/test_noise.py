from backend.detection.noise_gate import NoiseGate
from backend.detection.baselines import RobustMetricBaseline

def test_transient_spike_suppressed():
    gate = NoiseGate(persistence_windows=2)
    # Window 1: high z-score, but only 1 window and 1 signal
    decision, reasons = gate.evaluate(
        service_id="payment-service",
        z_scores={"latency": 4.5},
        cusum_scores={"latency": 2.0},
        has_trace_evidence=False,
        has_log_evidence=False,
        is_slo_breach=False,
        sample_count=20
    )
    assert decision == "SUPPRESSED"
    assert "Transient spike" in reasons[0]
    assert len(gate.suppressed_events_log) == 1

def test_sustained_multi_signal_confirmed():
    gate = NoiseGate(persistence_windows=2)
    # Window 1
    gate.evaluate("redis-replica-a", {"latency": 5.0}, {"latency": 4.5}, True, False, False, 20)
    # Window 2: sustained across 2 windows with trace evidence + metric z
    decision, reasons = gate.evaluate(
        service_id="redis-replica-a",
        z_scores={"latency": 5.2},
        cusum_scores={"latency": 6.0},
        has_trace_evidence=True,
        has_log_evidence=True,
        is_slo_breach=False,
        sample_count=25
    )
    assert decision == "CONFIRMED"
    assert "Sustained anomaly across 2 windows" in reasons[0]

def test_insufficient_telemetry():
    gate = NoiseGate(persistence_windows=2)
    decision, reasons = gate.evaluate(
        service_id="new-service",
        z_scores={"latency": 10.0},
        cusum_scores={"latency": 10.0},
        has_trace_evidence=True,
        has_log_evidence=True,
        is_slo_breach=False,
        sample_count=2 # < 5
    )
    assert decision == "INSUFFICIENT_TELEMETRY"

def test_robust_baseline_drift():
    b = RobustMetricBaseline("latency", window_size=30)
    # Feed normal values around 50ms
    for v in [50, 52, 48, 51, 49, 50, 53, 47, 50, 51, 49, 52]:
        b.update(v)

    assert abs(b.median - 50.0) <= 2.0
    # Normal value should have small z-score
    z_norm = b.compute_robust_z(52.0)
    assert abs(z_norm) < 2.0

    # Large spike should have large robust z-score
    z_spike = b.compute_robust_z(400.0)
    assert z_spike > 5.0

