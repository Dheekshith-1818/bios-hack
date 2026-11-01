from typing import List, Union, Dict, Any
import time
from backend.schemas import MetricEvent, TraceSpan, LogEvent
from backend.telemetry.aggregate import telemetry_aggregator
from backend.telemetry.spans import span_processor

class TelemetryIngestService:
    def __init__(self):
        self.live_graph_callback = None

    def register_graph_callback(self, cb):
        self.live_graph_callback = cb

    def ingest_metric(self, metric: MetricEvent):
        telemetry_aggregator.ingest_metric(metric)

    def ingest_metrics_batch(self, metrics: List[MetricEvent]):
        for m in metrics:
            telemetry_aggregator.ingest_metric(m)

    def ingest_span(self, span: TraceSpan):
        telemetry_aggregator.ingest_span(span)
        edge_info = span_processor.ingest_span(span)
        if edge_info and self.live_graph_callback:
            caller, callee, duration_ms, is_err = edge_info
            self.live_graph_callback(caller, callee, duration_ms, is_err, span.endTs)

    def ingest_spans_batch(self, spans: List[TraceSpan]):
        for s in spans:
            self.ingest_span(s)

    def ingest_log(self, log: LogEvent):
        telemetry_aggregator.ingest_log(log)

    def ingest_logs_batch(self, logs: List[LogEvent]):
        for l in logs:
            telemetry_aggregator.ingest_log(l)

telemetry_ingest = TelemetryIngestService()

