import time
from typing import Dict, Any, Optional
from backend.simulator.world import SimulatorWorld

class ScenarioManager:
    def __init__(self, world: SimulatorWorld):
        self.world = world
        self.active_scenario_name = "idle"
        self.scenario_start_ts = 0.0

    def start_scenario(self, scenario_name: str) -> Dict[str, Any]:
        self.world.clear_faults()
        self.active_scenario_name = scenario_name
        self.scenario_start_ts = time.time()

        if scenario_name == "transient-spike":
            # 1-window latency spike on payment-service
            self.world.inject_fault(
                target_id="payment-service",
                fault_type="latency_spike",
                severity=1.2,
                metadata={"duration_windows": 1, "description": "Single-window network blip"}
            )
            return {
                "scenario": scenario_name,
                "description": "Transient 1-window payment latency spike. Expected: noise gate suppression, 0 false incidents.",
                "target": "payment-service"
            }

        elif scenario_name == "cache-cascade":
            # Redis replica A saturation
            self.world.inject_fault(
                target_id="redis-replica-a",
                fault_type="cache_saturation",
                severity=1.5,
                metadata={"description": "Redis replica-a partition/slowdown causing cascading latency"}
            )
            return {
                "scenario": scenario_name,
                "description": "Cache replica failure and cascade. Expected: RCA isolates replica-a, proposes reroute 10% to B, canary promotes to recovery.",
                "target": "redis-replica-a"
            }

        elif scenario_name == "bad-deployment":
            # Faulty payment service deployment
            self.world.set_service_revision("payment-service", "v2.0.0-rc1", 100.0)
            self.world.inject_fault(
                target_id="payment-service",
                fault_type="faulty_deployment",
                severity=1.0,
                metadata={"description": "Faulty release v2 raising 5xx errors on payment-service"}
            )
            return {
                "scenario": scenario_name,
                "description": "Faulty deployment on payment-service. Expected: RCA identifies payment v2, policy requires approval, canary rolls back to v1.4.2.",
                "target": "payment-service"
            }

        elif scenario_name == "unsafe-remediation":
            # Fault where treatment remediation causes regression
            self.world.inject_fault(
                target_id="identity-service",
                fault_type="unsafe_canary_regression",
                severity=1.4,
                metadata={"description": "Remediation candidate induces guardrail regression during canary"}
            )
            return {
                "scenario": scenario_name,
                "description": "Unsafe remediation caught by canary. Expected: Guardrail breach detected at 10% canary, immediate rollback before full rollout.",
                "target": "identity-service"
            }

        elif scenario_name == "idle":
            return {"scenario": "idle", "description": "Normal steady-state operation."}

        else:
            raise ValueError(f"Unknown scenario '{scenario_name}'")

    def step(self, current_ts: float):
        # Auto-clear transient spike after 1 window (~6 seconds)
        if self.active_scenario_name == "transient-spike":
            if time.time() - self.scenario_start_ts > 6.0:
                self.world.clear_faults()
                self.active_scenario_name = "idle"

    def reset(self):
        self.world.reset()
        self.active_scenario_name = "idle"
        self.scenario_start_ts = 0.0

