import argparse
import json
import sys
from backend.evaluation.scoring import benchmark_evaluator

def main():
    parser = argparse.ArgumentParser(description="CivicGuard Autopilot Evaluation Benchmark")
    parser.add_argument("--runs", type=int, default=32, help="Number of benchmark evaluation iterations")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    args = parser.parse_args()

    summary = benchmark_evaluator.compute_summary()

    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print("=" * 65)
        print("  CIVICGUARD AUTOPILOT — EVALUATION BENCHMARK RESULTS")
        print("=" * 65)
        print(f"Total Benchmark Runs: {summary['total_runs']}")
        print("-" * 65)
        print(f"{'METRIC':<30} | {'TARGET':<12} | {'MEASURED':<12}")
        print("-" * 65)
        m = summary["measured"]
        t = summary["targets"]
        print(f"{'Detection Precision':<30} | {t['precision']:<12} | {m['precision']}%")
        print(f"{'Detection Recall':<30} | {t['recall']:<12} | {m['recall']}%")
        print(f"{'Transient Noise Suppression':<30} | {t['transient_suppression_rate']:<12} | {m['transient_suppression_rate']}%")
        print(f"{'Top-1 Root Cause Accuracy':<30} | {t['top1_rca_accuracy']:<12} | {m['top1_rca_accuracy']}%")
        print(f"{'Mean Time to Identify (MTTI)':<30} | {t['avg_mtti_seconds']:<12} | {m['avg_mtti_seconds']}s")
        print(f"{'Mean Time to Recover (MTTR)':<30} | {t['avg_mttr_seconds']:<12} | {m['avg_mttr_seconds']}s")
        print(f"{'Full-Rollout Regressions':<30} | {t['full_rollout_regressions']:<12} | {m['full_rollout_regressions']}")
        print(f"{'Canary-Caught Regressions':<30} | {'N/A':<12} | {m['canary_caught_regressions']}")
        print("=" * 65)

if __name__ == "__main__":
    main()

