import time
from typing import Dict, Any
from backend.schemas import ActionProposal

class SimulatorExecutor:
    def __init__(self):
        self.world_ref = None

    def set_world(self, world):
        self.world_ref = world

    def apply_action(self, proposal: ActionProposal, percent: float) -> Dict[str, Any]:
        """
        Applies changes to the active simulation world model:
        - reroute_canary: changes traffic split between cache replicas
        - rollback_release: rolls back payment-service revision
        - scale_up: increases worker replicas
        """
        if not self.world_ref:
            return {"applied": False, "reason": "Simulator world not bound"}

        act_type = proposal.actionType
        target = proposal.targetId
        params = proposal.changeParameters

        if act_type == "reroute_canary":
            src = params.get("source_replica", "redis-replica-a")
            dst = params.get("destination_replica", "redis-replica-b")
            self.world_ref.set_traffic_split(src, dst, percent)
            return {"applied": True, "split": f"{100-percent}% -> {src}, {percent}% -> {dst}"}

        elif act_type == "rollback_release":
            target_rev = params.get("target_revision", "v1.4.2")
            self.world_ref.set_service_revision(target, target_rev, percent)
            return {"applied": True, "revision": target_rev, "percent": percent}

        elif act_type == "scale_up":
            delta = params.get("replica_delta", 2)
            self.world_ref.scale_service(target, delta)
            return {"applied": True, "scaled_by": delta}

        return {"applied": True, "action": act_type}

    def revert_action(self, proposal: ActionProposal) -> Dict[str, Any]:
        if not self.world_ref:
            return {"reverted": False, "reason": "Simulator world not bound"}

        act_type = proposal.actionType
        target = proposal.targetId

        if act_type == "reroute_canary":
            self.world_ref.set_traffic_split("redis-replica-a", "redis-replica-b", 0.0)
            return {"reverted": True, "traffic_reset": "100% replica-a"}

        elif act_type == "rollback_release":
            self.world_ref.set_service_revision(target, "v2.0.0-rc1", 0.0)
            return {"reverted": True, "revision_reset": "v2.0.0-rc1"}

        return {"reverted": True}

simulator_executor = SimulatorExecutor()

