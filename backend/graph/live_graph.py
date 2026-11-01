import time
from typing import Dict, Any, Optional
from backend.graph.topology import DependencyGraph
from backend.telemetry.ingest import telemetry_ingest
from backend.store import store
from backend.schemas import TopologySnapshot

class LiveGraphManager:
    def __init__(self):
        self.graph = DependencyGraph()
        telemetry_ingest.register_graph_callback(self.on_span_edge)
        self.last_snapshot_ts = 0.0

    def on_span_edge(self, caller: str, callee: str, duration_ms: float, is_error: bool, ts: float):
        self.graph.record_edge_observation(caller, callee, duration_ms, is_error, ts)
        # Periodically persist snapshot every 30s
        now = time.time()
        if now - self.last_snapshot_ts > 30.0:
            snapshot = self.graph.to_snapshot()
            store.save_topology_snapshot(snapshot)
            self.last_snapshot_ts = now

    def update_node_status(self, service_id: str, health_status: str, normalized_metrics: Optional[Dict[str, float]] = None):
        if self.graph.g.has_node(service_id):
            self.graph.g.nodes[service_id]["health_status"] = health_status
            if normalized_metrics:
                self.graph.g.nodes[service_id]["normalized_metrics"] = normalized_metrics
            self.graph.version += 1

    def prune(self, current_ts: Optional[float] = None):
        ts = current_ts or time.time()
        self.graph.prune_stale_edges(ts)

    def get_snapshot(self) -> TopologySnapshot:
        return self.graph.to_snapshot()

    def reset(self):
        self.graph = DependencyGraph()
        self.last_snapshot_ts = 0.0

live_graph = LiveGraphManager()

