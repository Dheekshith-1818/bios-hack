import sys
import os
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from backend.main import app

def run_smoke_test():
    print("[Smoke Test] Initializing TestClient...")
    client = TestClient(app)

    print("[Smoke Test] 1. Checking /api/health...")
    r = client.get("/api/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print(f"  -> Health OK: {r.json()['service']} v{r.json()['version']}")

    print("[Smoke Test] 2. Checking /api/state...")
    r = client.get("/api/state")
    assert r.status_code == 200
    state = r.json()
    print(f"  -> Active Scenario: {state['activeScenario']}, Nodes: {len(state['graph']['nodes'])}")

    print("[Smoke Test] 3. Starting Transient Spike Scenario...")
    r = client.post("/api/simulations/transient-spike/start")
    assert r.status_code == 200
    print(f"  -> Scenario started: {r.json()['scenario']}")

    print("[Smoke Test] 4. Verifying Audit Ledger...")
    r = client.get("/api/audit/verify")
    assert r.status_code == 200
    verif = r.json()
    assert verif["valid"] is True
    print(f"  -> Audit Ledger Valid: {verif['total_events']} events verified")

    print("[Smoke Test] 5. Checking Benchmark Evaluation...")
    r = client.get("/api/evaluation/latest")
    assert r.status_code == 200
    eval_res = r.json()
    print(f"  -> Precision: {eval_res['measured']['precision']}%, RCA Acc: {eval_res['measured']['top1_rca_accuracy']}%")

    print("\n[Smoke Test] ALL CHECKS PASSED SUCCESSFULLY!\n")

if __name__ == "__main__":
    run_smoke_test()
