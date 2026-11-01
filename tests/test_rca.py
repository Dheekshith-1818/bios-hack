import time
from backend.diagnosis.root_cause import root_cause_ranker
from backend.graph.live_graph import live_graph
from backend.telemetry.aggregate import telemetry_aggregator
from backend.schemas import LogEvent, TraceSpan

def test_root_cause_ranking_ranks_cache_over_callers():
    # Setup topology: caller (identity-service) -> callee (redis-replica-a)
    live_graph.graph.record_edge_observation("identity-service", "redis-replica-a", 150.0, True, time.time())
    live_graph.graph.record_edge_observation("citizen-portal", "identity-service", 200.0, True, time.time())

    # Simulate earliest onset on redis-replica-a
    now = time.time()
    onset_times = {
        "redis-replica-a": now - 10.0, # Earliest onset
        "identity-service": now - 5.0,
        "citizen-portal": now - 2.0
    }

    # Add error log to redis-replica-a
    telemetry_aggregator.ingest_log(LogEvent(
        serviceId="redis-replica-a",
        severity="CRITICAL",
        eventType="CACHE_CONNECTION_TIMEOUT",
        message="Connection pool exhausted on replica A"
    ))

    # Add error span to redis-replica-a
    telemetry_aggregator.ingest_span(TraceSpan(
        traceId="t-rca-1",
        spanId="s-rca-1",
        startTs=now,
        endTs=now + 0.5,
        duration_ms=500.0,
        serviceId="redis-replica-a",
        operation="GET /key",
        status="ERROR"
    ))

    candidates = root_cause_ranker.rank_candidates(
        anomalous_services=["citizen-portal", "identity-service", "redis-replica-a"],
        onset_times=onset_times
    )

    assert len(candidates) >= 1
    top = candidates[0]
    # Redis replica A should rank first because of earliest onset, callee position, and direct errors
    assert top.serviceId == "redis-replica-a"
    assert top.score >= 70.0
    assert len(top.supportingEvidenceRefs) >= 2

