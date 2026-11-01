import time
from backend.graph.topology import DependencyGraph
from backend.telemetry.spans import SpanProcessor
from backend.schemas import TraceSpan

def test_span_creates_dependency_edge():
    processor = SpanProcessor()
    graph = DependencyGraph()

    # Create parent span in caller service and child in callee service
    t_id = "trace-101"
    p_span = TraceSpan(
        traceId=t_id,
        spanId="span-caller-1",
        parentSpanId=None,
        startTs=100.0,
        endTs=100.5,
        duration_ms=500.0,
        serviceId="citizen-portal",
        operation="GET /claims"
    )
    processor.ingest_span(p_span)

    c_span = TraceSpan(
        traceId=t_id,
        spanId="span-callee-1",
        parentSpanId="span-caller-1",
        startTs=100.1,
        endTs=100.4,
        duration_ms=300.0,
        serviceId="identity-service",
        operation="POST /verify"
    )
    edge_info = processor.ingest_span(c_span)
    assert edge_info is not None
    caller, callee, dur, is_err = edge_info
    assert caller == "citizen-portal"
    assert callee == "identity-service"
    assert dur == 300.0
    assert not is_err

    # Record into topology graph
    graph.record_edge_observation(caller, callee, dur, is_err, 100.4)
    assert graph.g.has_edge("citizen-portal", "identity-service")
    assert graph.get_callers("identity-service") == ["citizen-portal"]
    assert graph.get_callees("citizen-portal") == ["identity-service"]

def test_unlinked_services_have_no_edge():
    graph = DependencyGraph()
    graph.record_node_observation("service-alpha", 10.0)
    graph.record_node_observation("service-beta", 10.0)
    assert not graph.g.has_edge("service-alpha", "service-beta")
    assert not graph.g.has_edge("service-beta", "service-alpha")

def test_stale_edge_pruning():
    graph = DependencyGraph(edge_ttl_seconds=30.0)
    graph.record_edge_observation("caller-a", "callee-b", 50.0, False, ts=100.0)
    assert graph.g.has_edge("caller-a", "callee-b")

    # Prune at ts=140.0 (>30s older)
    graph.prune_stale_edges(current_ts=140.0)
    assert not graph.g.has_edge("caller-a", "callee-b")

def test_call_direction_vs_cascade_direction():
    graph = DependencyGraph()
    # Call direction: Portal -> Identity -> Cache
    graph.record_edge_observation("citizen-portal", "identity-service", 20.0, False, ts=1.0)
    graph.record_edge_observation("identity-service", "redis-cache", 5.0, False, ts=1.0)

    # In call graph: portal calls identity, identity calls cache
    assert graph.get_callees("citizen-portal") == ["identity-service"]
    assert graph.get_callees("identity-service") == ["redis-cache"]

    # In failure cascade: cache fails -> spreads to identity -> spreads to portal!
    paths = graph.get_reverse_dependency_paths("redis-cache")
    assert len(paths) >= 1
    # Cache to identity to portal
    full_path = [p for p in paths if p == ["redis-cache", "identity-service", "citizen-portal"]]
    assert len(full_path) == 1

