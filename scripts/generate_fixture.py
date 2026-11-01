import json
from pathlib import Path
from backend.simulator.fixtures import SERVICES, HIDDEN_TOPOLOGY, BASE_LATENCIES_MS

def main():
    fixture_data = {
        "services": SERVICES,
        "hidden_topology": HIDDEN_TOPOLOGY,
        "base_latencies_ms": BASE_LATENCIES_MS,
        "scenarios": [
            "transient-spike",
            "cache-cascade",
            "bad-deployment",
            "unsafe-remediation"
        ]
    }
    out_path = Path(__file__).resolve().parent.parent / "data" / "fixtures.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fixture_data, f, indent=2)
    print(f"Generated fixture at {out_path}")

if __name__ == "__main__":
    main()

