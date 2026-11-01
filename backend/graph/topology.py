import networkx as nx
from typing import Dict, List, Optional, Set, Tuple
import time
import numpy as np
from backend.schemas import GraphNode, GraphEdge, TopologySnapshot

class DependencyGraph:
    def __init__(self, edge_ttl_seconds: float = 90.0, min_observations: int = 2):
        self.edge_ttl_seconds = edge_ttl_seconds
        self.min_observations = min_observations
        # DiGraph where edges are caller -> callee (caller depends on callee)
        self.g = nx.DiGraph()
        self.version = 1
        self._edge_latencies: Dict[Tuple[str, str], List[float]] = {}
        self._edge_errors: Dict[Tuple[str, str], int] = {}
        self._edge_calls: Dict[Tuple[str, str], int] = {}
        self._edge_last_seen: Dict[Tuple[str, str], float] = {}

    def record_edge_observation(self, caller: str, callee: str, latency_ms: float, is_error: bool, ts: float):
        self.record_node_observation(caller, ts)
        self.record_node_observation(callee, ts)

        edge_key = (caller, callee)
        if edge_key not in self._edge_latencies:
            self._edge_latencies[edge_key] = []
            self._edge_errors[edge_key] = 0
            self._edge_calls[edge_key] = 0

        self._edge_latencies[edge_key].append(latency_ms)
        if len(self._edge_latencies[edge_key]) > 200:
            self._edge_latencies[edge_key].pop(0)

        if is_error:
            self._edge_errors[edge_key] += 1
        self._edge_calls[edge_key] += 1
        self._edge_last_seen[edge_key] = ts

        calls = self._edge_calls[edge_key]
        errs = self._edge_errors[edge_key]
        lat_arr = np.array(self._edge_latencies[edge_key])
        p50 = float(np.percentile(lat_arr, 50))
        p95 = float(np.percentile(lat_arr, 95))
        err_rate = errs / max(1, calls)
        confidence = min(1.0, calls / float(self.min_observations * 5))

        self.g.add_edge(
            caller, callee,
            call_count=calls,
            last_seen=ts,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            error_rate=err_rate,
            confidence=confidence,
            stale=False
        )
        self.version += 1

    def record_node_observation(self, service_id: str, ts: float, labels: Optional[Dict[str, str]] = None):
        if not self.g.has_node(service_id):
            self.g.add_node(
                service_id,
                labels=labels or {},
                evidence_count=1,
                last_seen=ts,
                health_status="HEALTHY",
                normalized_metrics={},
                recent_changes=[],
                stale=False
            )
            self.version += 1
        else:
            self.g.nodes[service_id]["last_seen"] = ts
            self.g.nodes[service_id]["evidence_count"] += 1
            if labels:
                self.g.nodes[service_id]["labels"].update(labels)

    def prune_stale_edges(self, current_ts: float):
        cutoff = current_ts - self.edge_ttl_seconds
        removed_any = False
        edges_to_remove = []

        for u, v, data in self.g.edges(data=True):
            last_seen = data.get("last_seen", 0)
            if last_seen < cutoff:
                edges_to_remove.append((u, v))

        for u, v in edges_to_remove:
            self.g.remove_edge(u, v)
            self._edge_latencies.pop((u, v), None)
            self._edge_errors.pop((u, v), None)
            self._edge_calls.pop((u, v), None)
            self._edge_last_seen.pop((u, v), None)
            removed_any = True

        if removed_any:
            self.version += 1

    def get_callers(self, service_id: str) -> List[str]:
        """
        Returns nodes that call service_id (i.e. nodes that depend on service_id).
        In failure cascade, failure travels from service_id to its callers!
        """
        if not self.g.has_node(service_id):
            return []
        return list(self.g.predecessors(service_id))

    def get_callees(self, service_id: str) -> List[str]:
        """
        Returns nodes that service_id calls (i.e. dependencies of service_id).
        """
        if not self.g.has_node(service_id):
            return []
        return list(self.g.successors(service_id))

    def get_reverse_dependency_paths(self, root_service_id: str, max_depth: int = 4) -> List[List[str]]:
        """
        Traverses reverse dependencies (callee -> callers) to trace failure propagation outward.
        """
        if not self.g.has_node(root_service_id):
            return []

        # Reverse graph so edge u -> v means u is callee, v is caller (propagation direction)
        rev_g = self.g.reverse(copy=True)
        paths = []

        for target in rev_g.nodes():
            if target != root_service_id and nx.has_path(rev_g, root_service_id, target):
                try:
                    all_p = list(nx.all_simple_paths(rev_g, root_service_id, target, cutoff=max_depth))
                    paths.extend(all_p)
                except Exception:
                    pass

        return paths

    def to_snapshot(self) -> TopologySnapshot:
        nodes = []
        for n, d in self.g.nodes(data=True):
            nodes.append(GraphNode(
                id=n,
                labels=d.get("labels", {}),
                evidenceCount=d.get("evidence_count", 0),
                lastSeen=d.get("last_seen", time.time()),
                healthStatus=d.get("health_status", "HEALTHY"),
                normalizedMetrics=d.get("normalized_metrics", {}),
                recentChanges=d.get("recent_changes", []),
                stale=d.get("stale", False)
            ))

        edges = []
        for u, v, d in self.g.edges(data=True):
            edges.append(GraphEdge(
                id=f"{u}->{v}",
                caller=u,
                callee=v,
                callCount=d.get("call_count", 0),
                lastSeen=d.get("last_seen", time.time()),
                p50_latency_ms=round(d.get("p50_latency_ms", 0.0), 2),
                p95_latency_ms=round(d.get("p95_latency_ms", 0.0), 2),
                errorRate=round(d.get("error_rate", 0.0), 4),
                confidence=round(d.get("confidence", 1.0), 2),
                stale=d.get("stale", False)
            ))

        return TopologySnapshot(
            version=self.version,
            timestamp=time.time(),
            nodes=nodes,
            edges=edges
        )

