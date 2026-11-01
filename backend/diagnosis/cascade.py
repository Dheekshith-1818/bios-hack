import time
from typing import Dict, List, Set
from backend.graph.live_graph import live_graph
from backend.schemas import CascadePrediction, CascadeNodeImpact

class CascadePredictor:
    def __init__(self, decay_factor: float = 0.75, max_hops: int = 4):
        self.decay_factor = decay_factor
        self.max_hops = max_hops

    def predict_cascade(self, starting_node: str) -> CascadePrediction:
        """
        Traverses reverse dependency edges (callee -> callers) from starting_node.
        Failure spreads outward to callers that depend on this callee!
        """
        g = live_graph.graph.g
        impacts: Dict[str, CascadeNodeImpact] = {}
        paths: List[List[str]] = []

        if not g.has_node(starting_node):
            return CascadePrediction(startingNode=starting_node)

        # BFS / Dijkstra outward on reverse graph
        # Queue: (current_node, current_risk, path)
        queue = [(starting_node, 1.0, [starting_node])]
        visited: Set[str] = {starting_node}

        while queue:
            curr, risk, path = queue.pop(0)

            if len(path) > self.max_hops:
                continue

            # Callers of curr are the ones that depend on curr!
            callers = live_graph.graph.get_callers(curr)
            for caller in callers:
                # Get edge metrics if available
                edge_data = g.get_edge_data(caller, curr, default={})
                confidence = edge_data.get("confidence", 0.8)
                err_rate = edge_data.get("error_rate", 0.0)

                # Propagation risk decreases with hop distance and edge confidence
                propagated_risk = risk * self.decay_factor * (0.5 + 0.5 * confidence)

                new_path = path + [caller]
                paths.append(new_path)

                if caller not in impacts or propagated_risk > impacts[caller].propagationRisk:
                    expected_lat = round(propagated_risk * 120.0, 1) # ms
                    expected_err = round(min(0.8, propagated_risk * 0.25 + err_rate), 3)

                    impacts[caller] = CascadeNodeImpact(
                        serviceId=caller,
                        propagationRisk=round(propagated_risk, 3),
                        expectedLatencyIncreasePct=round(propagated_risk * 50.0, 1),
                        expectedErrorRate=expected_err,
                        pathFromRoot=new_path
                    )

                if caller not in visited:
                    visited.add(caller)
                    queue.append((caller, propagated_risk, new_path))

        overall_risk = max([imp.propagationRisk for imp in impacts.values()], default=0.0)

        return CascadePrediction(
            startingNode=starting_node,
            predictedImpact=impacts,
            dependencyPaths=paths,
            overallPropagationRisk=round(overall_risk, 3),
            modelAssumptions="Deterministic reverse-dependency multi-hop propagation with traffic-weighted decay",
            generatedAt=time.time()
        )

cascade_predictor = CascadePredictor()

