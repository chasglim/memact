#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


THIS_FILE = Path(__file__).resolve()
EXPERIMENT_DIR = THIS_FILE.parent
REPO_ROOT = EXPERIMENT_DIR.parent.parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from memoryact_exp.runner import run_benchmark  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the MemAct instrumented multi-tenant cloud-agent benchmark.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=EXPERIMENT_DIR / "results",
        help="Directory for generated tables and per-task JSONL.",
    )
    parser.add_argument(
        "--tasks-per-scenario",
        type=int,
        default=40,
        help="Number of tasks per scenario. Default gives 120 total tasks.",
    )
    parser.add_argument(
        "--memories-per-tenant-scenario",
        type=int,
        default=50,
        help="Number of memory capsules per tenant per scenario. Default gives 750 total memories.",
    )
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument(
        "--no-ablation",
        action="store_true",
        help="Skip MemAct ablation table generation.",
    )
    parser.add_argument(
        "--memkernel-bin",
        default=None,
        help="Optional path to the existing memkernel CLI binary.",
    )
    parser.add_argument(
        "--skip-memkernel-smoke",
        action="store_true",
        help="Do not run the memkernel CLI reuse smoke test.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run_benchmark(
        repo_root=REPO_ROOT,
        output_dir=args.output,
        tasks_per_scenario=args.tasks_per_scenario,
        memories_per_tenant_scenario=args.memories_per_tenant_scenario,
        candidate_k=args.candidate_k,
        final_k=args.final_k,
        run_ablation=not args.no_ablation,
        memkernel_bin=args.memkernel_bin,
        skip_memkernel_smoke=args.skip_memkernel_smoke,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
