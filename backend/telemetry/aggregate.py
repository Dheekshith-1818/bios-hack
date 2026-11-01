import time
import numpy as np
from typing import Dict, List, Any, Optional
from collections import deque, defaultdict
from backend.schemas import MetricEvent, LogEvent, TraceSpan

class ServiceWindowMetrics:
    def __init__(self, window_size: int = 60):
        self.latencies = deque(maxlen=window_size * 20)
        self.error_count = 0
        self.total_requests = 0
        self.cpu_samples = deque(maxlen=window_size)
        self.memory_samples = deque(maxlen=window_size)
        self.log_counts = defaultdict(int)
        self.recent_logs: deque[LogEvent] = deque(maxlen=50)
        self.last_updated = time.time()

    def add_latency(self, val_ms: float):
        self.latencies.append(val_ms)
        self.total_requests += 1

    def add_error(self):
        self.error_count += 1
        self.total_requests += 1

    def add_metric(self, name: str, val: float):
        if name in ("cpu_percent", "cpu_utilization"):
            self.cpu_samples.append(val)
        elif name in ("memory_percent", "memory_utilization"):
            self.memory_samples.append(val)
        elif name in ("latency_ms", "request_duration_ms"):
            self.add_latency(val)
        elif name in ("error_count", "errors_total"):
            self.error_count += int(val)
        elif name in ("request_count", "requests_total"):
            self.total_requests += int(val)
        self.last_updated = time.time()

    def add_log(self, log: LogEvent):
        self.log_counts[f"{log.severity}:{log.eventType}"] += 1
        self.recent_logs.append(log)
        self.last_updated = time.time()

    def summary(self) -> Dict[str, float]:
        l_arr = np.array(self.latencies) if self.latencies else np.array([0.0])
        p50 = float(np.percentile(l_arr, 50)) if len(l_arr) > 0 else 0.0
        p95 = float(np.percentile(l_arr, 95)) if len(l_arr) > 0 else 0.0
        p99 = float(np.percentile(l_arr, 99)) if len(l_arr) > 0 else 0.0
        err_rate = (self.error_count / max(1, self.total_requests)) if self.total_requests > 0 else 0.0
        cpu = float(np.mean(self.cpu_samples)) if self.cpu_samples else 0.0

        return {
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "p99_latency_ms": round(p99, 2),
            "error_rate": round(err_rate, 4),
            "throughput_rps": round(self.total_requests / 5.0, 1),
            "cpu_percent": round(cpu, 1),
            "sample_count": len(self.latencies) + self.total_requests
        }

class TelemetryAggregator:
    def __init__(self):
        self.services: Dict[str, ServiceWindowMetrics] = defaultdict(ServiceWindowMetrics)
        self.raw_metrics_buffer: deque[MetricEvent] = deque(maxlen=2000)
        self.raw_logs_buffer: deque[LogEvent] = deque(maxlen=1000)
        self.raw_spans_buffer: deque[TraceSpan] = deque(maxlen=2000)

    def ingest_metric(self, metric: MetricEvent):
        self.raw_metrics_buffer.append(metric)
        self.services[metric.serviceId].add_metric(metric.name, metric.value)

    def ingest_log(self, log: LogEvent):
        self.raw_logs_buffer.append(log)
        self.services[log.serviceId].add_log(log)

    def ingest_span(self, span: TraceSpan):
        self.raw_spans_buffer.append(span)
        srv = self.services[span.serviceId]
        srv.add_latency(span.duration_ms)
        if span.status == "ERROR":
            srv.add_error()

    def get_service_summary(self, service_id: str) -> Dict[str, float]:
        return self.services[service_id].summary()

    def get_all_summaries(self) -> Dict[str, Dict[str, float]]:
        return {s_id: m.summary() for s_id, m in self.services.items()}

    def get_recent_logs(self, service_id: Optional[str] = None, limit: int = 50) -> List[LogEvent]:
        if service_id:
            return list(self.services[service_id].recent_logs)[-limit:]
        return list(self.raw_logs_buffer)[-limit:]

    def get_recent_spans(self, service_id: Optional[str] = None, limit: int = 50) -> List[TraceSpan]:
        if service_id:
            return [s for s in self.raw_spans_buffer if s.serviceId == service_id][-limit:]
        return list(self.raw_spans_buffer)[-limit:]

telemetry_aggregator = TelemetryAggregator()

