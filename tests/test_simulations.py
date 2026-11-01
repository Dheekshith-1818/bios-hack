from backend.simulator.world import SimulatorWorld
from backend.simulator.scenarios import ScenarioManager

def test_simulation_world_steady_state():
    world = SimulatorWorld(seed=123)
    metrics, spans, logs = world.generate_step_telemetry(100.0)
    assert len(metrics) > 0
    assert len(spans) > 0
    # In steady state, error logs should be 0
    crit_logs = [l for l in logs if l.severity in ("ERROR", "CRITICAL")]
    assert len(crit_logs) == 0

def test_cache_cascade_scenario_diverts_to_replica_b():
    world = SimulatorWorld(seed=456)
    scenarios = ScenarioManager(world)
    scenarios.start_scenario("cache-cascade")

    # Injected fault should increase latency on replica A
    metrics, spans, logs = world.generate_step_telemetry(100.0)
    rep_a_metrics = [m for m in metrics if m.serviceId == "redis-replica-a" and m.name == "p95_latency_ms"]
    assert len(rep_a_metrics) == 1
    assert rep_a_metrics[0].value > 400.0

    # Simulate remediation reroute 100% to replica B
    world.set_traffic_split("redis-replica-a", "redis-replica-b", 100.0)
    m2, s2, l2 = world.generate_step_telemetry(110.0)
    rep_a_metrics2 = [m for m in m2 if m.serviceId == "redis-replica-a" and m.name == "p95_latency_ms"]
    assert rep_a_metrics2[0].value < 50.0

