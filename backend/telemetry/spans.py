from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from backend.schemas import TraceSpan

class SpanProcessor:
    def __init__(self, ttl_seconds: float = 60.0):
        self.ttl_seconds = ttl_seconds
        # In-memory buffer of recent spans: span_id -> TraceSpan
        self.spans_by_id: Dict[str, TraceSpan] = {}
        # trace_id -> list of span_ids
        self.traces: Dict[str, List[str]] = defaultdict(list)

    def ingest_span(self, span: TraceSpan) -> Optional[Tuple[str, str, float, bool]]:
        """
        Stores span and returns inferred dependency edge (caller, callee, duration_ms, is_error) if discernible.
        """
        self.spans_by_id[span.spanId] = span
        self.traces[span.traceId].append(span.spanId)

        # 1. Direct parent span linkage across services
        if span.parentSpanId and span.parentSpanId in self.spans_by_id:
            parent = self.spans_by_id[span.parentSpanId]
            if parent.serviceId != span.serviceId:
                is_error = (span.status == "ERROR" or parent.status == "ERROR")
                return (parent.serviceId, span.serviceId, span.duration_ms, is_error)

        # 2. Peer service attribute if explicitly provided
        if span.peerServiceId and span.peerServiceId != span.serviceId:
            is_error = (span.status == "ERROR")
            return (span.serviceId, span.peerServiceId, span.duration_ms, is_error)

        return None

    def prune_stale(self, current_ts: float):
        cutoff = current_ts - self.ttl_seconds
        to_del = [sid for sid, s in self.spans_by_id.items() if s.endTs < cutoff]
        for sid in to_del:
            s = self.spans_by_id.pop(sid, None)
            if s and s.traceId in self.traces:
                if sid in self.traces[s.traceId]:
                    self.traces[s.traceId].remove(sid)
                if not self.traces[s.traceId]:
                    self.traces.pop(s.traceId, None)

span_processor = SpanProcessor()

