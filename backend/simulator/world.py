import random
import time
import uuid
from typing import Dict, List, Any, Tuple
from backend.schemas import MetricEvent, TraceSpan, LogEvent
from backend.simulator.fixtures import SERVICES, HIDDEN_TOPOLOGY, BASE_LATENCIES_MS

class SimulatorWorld:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        
        # State variables altered by remediation
        self.cache_traffic_split = {"redis-replica-a": 100.0, "redis-replica-b": 0.0}
        self.service_revisions = {"payment-service": "v1.4.2"}
        self.service_replicas = {s: 2 for s in SERVICES}
        
        # Fault injection state
        self.faults: Dict[str, Dict[str, Any]] = {}

    def set_traffic_split(self, src: str, dst: str, percent: float):
        p = max(0.0, min(100.0, percent))
        self.cache_traffic_split[src] = 100.0 - p
        self.cache_traffic_split[dst] = p

    def set_service_revision(self, service_id: str, revision: str, rollout_percent: float):
        self.service_revisions[service_id] = revision

    def scale_service(self, service_id: str, delta: int):
        self.service_replicas[service_id] = max(1, self.service_replicas.get(service_id, 2) + delta)

    def inject_fault(self, target_id: str, fault_type: str, severity: float, metadata: Dict[str, Any] = None):
        self.faults[target_id] = {
            "fault_type": fault_type,
            "severity": severity,
            "metadata": metadata or {},
            "injected_at": time.time()
        }

    def clear_faults(self):
        self.faults.clear()

    def generate_step_telemetry(self, current_ts: float) -> Tuple[List[MetricEvent], List[TraceSpan], List[LogEvent]]:
        metrics: List[MetricEvent] = []
        spans: List[TraceSpan] = []
        logs: List[LogEvent] = []

        # Determine effective service health based on faults and remediations
        service_extra_lat: Dict[str, float] = {}
        service_extra_err: Dict[str, float] = {}

        # 1. Evaluate faults
        for target, f in self.faults.items():
            ftype = f["fault_type"]
            sev = f["severity"]
            if ftype == "latency_spike":
                service_extra_lat[target] = sev * 400.0
            elif ftype == "error_burst":
                service_extra_err[target] = min(0.9, sev * 0.45)
            elif ftype == "cache_saturation":
                # Only affects replica A according to traffic split!
                split_a = self.cache_traffic_split.get("redis-replica-a", 100.0) / 100.0
                effective_lat = sev * 550.0 * split_a
                service_extra_lat["redis-replica-a"] = effective_lat
                if effective_lat > 100.0:
                    service_extra_lat["identity-service"] = effective_lat * 0.8
                    service_extra_lat["citizen-portal"] = effective_lat * 0.65
            elif ftype == "faulty_deployment":
                rev = self.service_revisions.get("payment-service", "v1.4.2")
                if "v2" in rev:
                    service_extra_err["payment-service"] = 0.28
                    service_extra_lat["payment-service"] = 180.0
            elif ftype == "unsafe_canary_regression":
                # Simulated regression during treatment
                service_extra_err[target] = 0.35
                service_extra_lat[target] = 600.0

        # 2. Simulate user transactions through trace spans
        for _ in range(8):
            trace_id = str(uuid.uuid4())
            span_ids: Dict[str, str] = {}
            for s_id in SERVICES:
                span_ids[s_id] = str(uuid.uuid4())

            # Walk through call graph
            for caller, callee in HIDDEN_TOPOLOGY:
                # If target is redis-replica-a, respect traffic split
                actual_callee = callee
                if callee == "redis-replica-a":
                    split_b = self.cache_traffic_split.get("redis-replica-b", 0.0)
                    if self.rng.random() * 100.0 < split_b:
                        actual_callee = "redis-replica-b"

                base_mu, base_sigma = BASE_LATENCIES_MS.get(actual_callee, (20.0, 4.0))
                extra_l = service_extra_lat.get(actual_callee, 0.0)
                extra_e = service_extra_err.get(actual_callee, 0.0)

                dur = max(2.0, self.rng.gauss(base_mu, base_sigma) + extra_l)
                is_err = self.rng.random() < (0.002 + extra_e)
                status = "ERROR" if is_err else "OK"

                span = TraceSpan(
                    traceId=trace_id,
                    spanId=span_ids[actual_callee],
                    parentSpanId=span_ids[caller],
                    startTs=current_ts,
                    endTs=current_ts + (dur / 1000.0),
                    duration_ms=round(dur, 2),
                    serviceId=actual_callee,
                    peerServiceId=caller,
                    operation=f"HTTP /api/{actual_callee}",
                    status=status
                )
                spans.append(span)

                if is_err:
                    logs.append(LogEvent(
                        serviceId=actual_callee,
                        severity="ERROR",
                        eventType="DOWNSTREAM_CALL_FAILED",
                        message=f"Request to {actual_callee} returned status 503 Service Unavailable",
                        traceId=trace_id
                    ))

        # 3. Generate Service Metrics & Logs
        for s_id in SERVICES:
            extra_l = service_extra_lat.get(s_id, 0.0)
            extra_e = service_extra_err.get(s_id, 0.0)
            base_mu, _ = BASE_LATENCIES_MS.get(s_id, (20.0, 4.0))

            p95_val = round(base_mu * 1.5 + extra_l + self.rng.uniform(-3, 3), 2)
            err_val = round(0.002 + extra_e + self.rng.uniform(0, 0.002), 4)
            cpu_val = round(min(98.0, 25.0 + (extra_l * 0.12) + self.rng.uniform(0, 5)), 1)

            metrics.append(MetricEvent(serviceId=s_id, name="p95_latency_ms", value=p95_val, unit="ms", timestamp=current_ts))
            metrics.append(MetricEvent(serviceId=s_id, name="error_rate", value=err_val, unit="fraction", timestamp=current_ts))
            metrics.append(MetricEvent(serviceId=s_id, name="cpu_percent", value=cpu_val, unit="percent", timestamp=current_ts))

            # Emit structured logs if degraded
            if extra_l > 150.0:
                logs.append(LogEvent(
                    serviceId=s_id,
                    severity="WARN",
                    eventType="THREAD_POOL_SATURATION",
                    message=f"Thread pool exhaustion observed; connection latency {p95_val:.1f}ms exceeds threshold",
                    metadata={"p95_ms": p95_val}
                ))
            if extra_e > 0.05:
                logs.append(LogEvent(
                    serviceId=s_id,
                    severity="CRITICAL",
                    eventType="CIRCUIT_BREAKER_TRIGGERED",
                    message=f"Error rate {err_val*100:.1f}% tripped circuit breaker",
                    metadata={"error_rate": err_val}
                ))

        return metrics, spans, logs

    def reset(self):
        self.faults.clear()
        self.cache_traffic_split = {"redis-replica-a": 100.0, "redis-replica-b": 0.0}
        self.service_revisions = {"payment-service": "v1.4.2"}
        self.service_replicas = {s: 2 for s in SERVICES}

