import asyncio
import time
from typing import Dict, Any, List, Optional, Callable
from backend.simulator.world import SimulatorWorld
from backend.simulator.scenarios import ScenarioManager
from backend.telemetry.ingest import telemetry_ingest
from backend.detection.changepoints import changepoint_detector
from backend.incidents.lifecycle import incident_lifecycle
from backend.recovery.simulator_executor import simulator_executor
from backend.clock import sim_clock

class SimulationEngine:
    def __init__(self, seed: int = 42):
        self.world = SimulatorWorld(seed=seed)
        simulator_executor.set_world(self.world)
        self.scenarios = ScenarioManager(self.world)
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.step_interval_seconds = 2.0
        self.judge_mode_active = False
        self.judge_mode_step = 0
        self.judge_mode_start_ts = 0.0

    def register_broadcast_callback(self, cb: Callable[[Dict[str, Any]], Any]):
        self.broadcast_callback = cb

    async def start(self):
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def _run_loop(self):
        while self.running:
            try:
                if not sim_clock.is_paused:
                    now_v = sim_clock.now()
                    self.step(now_v)
                await asyncio.sleep(self.step_interval_seconds / sim_clock.speed)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SimulationEngine Error] {e}")
                await asyncio.sleep(1.0)

    def step(self, current_ts: float):
        # 1. Update active scenario
        self.scenarios.step(current_ts)

        # 2. Judge mode autonomous walkthrough state machine
        if self.judge_mode_active:
            self._handle_judge_mode_step()

        # 3. Generate synthetic telemetry
        metrics, spans, logs = self.world.generate_step_telemetry(current_ts)

        # 4. Ingest telemetry
        telemetry_ingest.ingest_metrics_batch(metrics)
        telemetry_ingest.ingest_spans_batch(spans)
        telemetry_ingest.ingest_logs_batch(logs)

        # 5. Detection cycle
        scan_res = changepoint_detector.scan_window()
        confirmed_srvs = scan_res.get("anomalies_detected", [])

        # 6. Incident Lifecycle handling
        if confirmed_srvs:
            # Map onset times
            onset_times = {s: current_ts - 2.0 for s in confirmed_srvs}
            inc = incident_lifecycle.create_or_update_incident(confirmed_srvs, onset_times)
            if inc and inc.status == "CONFIRMED":
                # Autonomously run diagnosis and propose proof
                proof = incident_lifecycle.diagnose_and_propose(inc.id, onset_times)
                if proof and proof.policyDecision.decision == "ALLOW" and inc.status == "POLICY_CHECKED":
                    # Autonomous auto-start canary for non-critical services or in judge mode
                    incident_lifecycle.approve_action(inc.id, operator_id="civicguard-autonomous-agent")

        # 7. Step active canaries
        for inc_id, inc in list(incident_lifecycle.active_incidents.items()):
            if inc.status in ("CANARY_RUNNING", "PROMOTING"):
                obs = inc.canaryObservation
                curr_pct = obs.percent if obs else 10.0
                obs_windows = (obs.windowsObserved + 1) if obs else 1

                # Gather control vs treatment metric measurements
                if "unsafe" in self.scenarios.active_scenario_name:
                    # Inject canary regression into treatment
                    ctrl_m = {"p95_latency_ms": 65.0, "error_rate": 0.004}
                    treat_m = {"p95_latency_ms": 520.0, "error_rate": 0.048}
                else:
                    # Successful canary progression
                    ctrl_m = {"p95_latency_ms": 60.0, "error_rate": 0.003}
                    treat_m = {"p95_latency_ms": 48.0, "error_rate": 0.002}

                incident_lifecycle.evaluate_canary(
                    incident_id=inc.id,
                    current_percent=curr_pct,
                    windows_observed=obs_windows,
                    control_metrics=ctrl_m,
                    treatment_metrics=treat_m
                )

        # 8. Broadcast websocket state update
        if self.broadcast_callback:
            try:
                self.broadcast_callback({
                    "type": "simulation_tick",
                    "timestamp": current_ts,
                    "active_scenario": self.scenarios.active_scenario_name,
                    "judge_mode": self.judge_mode_active,
                    "judge_step": self.judge_mode_step,
                    "confirmed_services": confirmed_srvs
                })
            except Exception:
                pass

    def start_judge_mode(self):
        self.reset()
        self.judge_mode_active = True
        self.judge_mode_step = 1
        self.judge_mode_start_ts = time.time()
        sim_clock.set_speed(1.5)

    def _handle_judge_mode_step(self):
        elapsed = time.time() - self.judge_mode_start_ts
        if self.judge_mode_step == 1 and elapsed > 4.0:
            # Step 1: Transient spike
            self.scenarios.start_scenario("transient-spike")
            self.judge_mode_step = 2
        elif self.judge_mode_step == 2 and elapsed > 14.0:
            # Step 2: Cache cascade
            self.scenarios.start_scenario("cache-cascade")
            self.judge_mode_step = 3
        elif self.judge_mode_step == 3 and elapsed > 36.0:
            # Step 3: Unsafe remediation test
            self.scenarios.start_scenario("unsafe-remediation")
            self.judge_mode_step = 4
        elif self.judge_mode_step == 4 and elapsed > 55.0:
            # Completed judge walkthrough
            self.judge_mode_active = False
            self.judge_mode_step = 5

    def reset(self):
        self.scenarios.reset()
        changepoint_detector.reset()
        incident_lifecycle.reset()
        self.judge_mode_active = False
        self.judge_mode_step = 0
        sim_clock.reset()

sim_engine = SimulationEngine()

