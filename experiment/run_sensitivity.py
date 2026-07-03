#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


THIS_FILE = Path(__file__).resolve()
EXPERIMENT_DIR = THIS_FILE.parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from memoryact_exp.dataset import (  # noqa: E402
    build_benchmark,
    build_clean_utility_benchmark,
    build_stress_benchmark,
)
from memoryact_exp.planner import draft_trace  # noqa: E402
from memoryact_exp.policy_checker import check_trace  # noqa: E402
from memoryact_exp.schemas import SelectionRecord  # noqa: E402
from memoryact_exp.selectors import MemoryActOptions, memoryact_select, select_for_method  # noqa: E402


METHODS = ["SimTopK", "CapsuleFilter", "PairwiseGate", "MemAct-Lite"]
DEFAULT_K = [3, 5, 10, 20, 40]
DEFAULT_N = [1, 2, 3, 5]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run candidate-budget sensitivity for the MemAct paper.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=EXPERIMENT_DIR / "results" / "table_vi_candidate_sensitivity.csv",
    )
    parser.add_argument("--final-k", type=int, default=5)
    parser.add_argument("--tasks-per-scenario", type=int, default=40)
    parser.add_argument("--memories-per-tenant-scenario", type=int, default=50)
    parser.add_argument("--candidate-k", type=int, nargs="+", default=DEFAULT_K)
    parser.add_argument(
        "--probe-output",
        type=Path,
        default=EXPERIMENT_DIR / "results" / "table_vii_probe_sensitivity.csv",
    )
    parser.add_argument(
        "--stress-output",
        type=Path,
        default=EXPERIMENT_DIR / "results" / "table_viii_stress_results.csv",
    )
    parser.add_argument(
        "--clean-output",
        type=Path,
        default=EXPERIMENT_DIR / "results" / "table_ix_clean_utility.csv",
    )
    parser.add_argument("--probe-n", type=int, nargs="+", default=DEFAULT_N)
    parser.add_argument("--stress-tasks-per-scenario", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks, memories = build_benchmark(
        tasks_per_scenario=args.tasks_per_scenario,
        memories_per_tenant_scenario=args.memories_per_tenant_scenario,
    )
    rows = []
    for candidate_k in args.candidate_k:
        for method in METHODS:
            rows.append(run_setting(tasks, memories, method, candidate_k, args.final_k))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {args.output}")

    stress_tasks, stress_memories = build_stress_benchmark(
        tasks_per_scenario=args.stress_tasks_per_scenario,
        memories_per_tenant_scenario=args.memories_per_tenant_scenario,
    )
    probe_rows = [
        run_setting(
            stress_tasks,
            stress_memories,
            "MemAct",
            40,
            args.final_k,
            probe_count=probe_n,
        )
        | {"ProbeN": str(probe_n)}
        for probe_n in args.probe_n
    ]
    args.probe_output.parent.mkdir(parents=True, exist_ok=True)
    with args.probe_output.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["ProbeN"] + [key for key in probe_rows[0].keys() if key != "ProbeN"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(probe_rows)
    print(f"Wrote {args.probe_output}")

    stress_methods = [
        "SimTopK",
        "Sim+Recency",
        "CapsuleFilter",
        "ToolGuardOnly",
        "PairwiseGate",
        "MemAct-Lite",
        "MemAct-Strict",
    ]
    stress_rows = [
        run_setting(
            stress_tasks,
            stress_memories,
            method,
            40,
            args.final_k,
        )
        for method in stress_methods
    ]
    args.stress_output.parent.mkdir(parents=True, exist_ok=True)
    with args.stress_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stress_rows[0].keys()))
        writer.writeheader()
        writer.writerows(stress_rows)
    print(f"Wrote {args.stress_output}")

    clean_tasks, clean_memories = build_clean_utility_benchmark(
        tasks_per_scenario=args.stress_tasks_per_scenario,
        memories_per_tenant_scenario=20,
    )
    clean_rows = [
        run_clean_utility_setting(clean_tasks, clean_memories, method, 5, args.final_k)
        for method in ["NoMemory", "DirectInject", "CapsuleFilter", "MemAct-Lite", "MemAct-Strict"]
    ]
    args.clean_output.parent.mkdir(parents=True, exist_ok=True)
    with args.clean_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(clean_rows[0].keys()))
        writer.writeheader()
        writer.writerows(clean_rows)
    print(f"Wrote {args.clean_output}")
    return 0


def run_setting(
    tasks,
    memories,
    method: str,
    candidate_k: int,
    final_k: int,
    probe_count: int = 1,
) -> dict[str, str]:
    totals = {
        "success": 0,
        "pc_success": 0,
        "any_violation": 0,
        "tokens": 0.0,
        "draft_calls": 0.0,
        "cand": 0.0,
    }
    selection_method = method
    for task in tasks:
        if selection_method == "MemAct" and probe_count != 1:
            selection = memoryact_select(
                task,
                memories,
                candidate_k,
                final_k,
                MemoryActOptions(probe_count=probe_count),
            )
        else:
            selection = select_for_method(selection_method, task, memories, candidate_k, final_k)
        baseline = draft_trace(task, [])
        trace = draft_trace(
            task,
            selection.memories,
            apply_tool_guard=selection.apply_tool_guard,
        )
        checks = check_trace(task, selection.memories, trace, baseline)
        totals["success"] += int(checks["success"])
        totals["pc_success"] += int(checks["success"] and checks["policy_compliant"])
        totals["any_violation"] += int(
            checks["unsafe_miad"]
            or checks["ctmir"]
            or checks["pvar"]
            or checks["utir"]
            or checks["smmr"]
        )
        totals["tokens"] += float(selection.record.token_estimate)
        totals["draft_calls"] += float(selection.record.llm_call_estimate)
        totals["cand"] += float(selection.record.decrypted_candidate_count)

    n = len(tasks) or 1
    return {
        "Method": method,
        "CandidateK": str(candidate_k),
        "ProbeN": str(probe_count),
        "Tasks": str(len(tasks)),
        "TSR": f"{100.0 * totals['success'] / n:.1f}",
        "PCSR": f"{100.0 * totals['pc_success'] / n:.1f}",
        "AnyViol": f"{100.0 * totals['any_violation'] / n:.1f}",
        "Tokens": f"{totals['tokens'] / n:.2f}",
        "DraftCalls": f"{totals['draft_calls'] / n:.2f}",
        "Cand.": f"{totals['cand'] / n:.2f}",
    }


def run_clean_utility_setting(
    tasks,
    memories,
    method: str,
    candidate_k: int,
    final_k: int,
) -> dict[str, str]:
    totals = {
        "success": 0,
        "useful_recall": 0.0,
        "false_rejection": 0.0,
        "tokens": 0.0,
        "draft_calls": 0.0,
        "cand": 0.0,
    }
    direct_reference = {
        task.id: select_for_method("SimTopK", task, memories, candidate_k, final_k).memories
        for task in tasks
    }
    for task in tasks:
        if method == "NoMemory":
            selection_memories = []
            record = SelectionRecord(
                method="NoMemory",
                selected_memory_ids=[],
                candidate_count=0,
                decrypted_candidate_count=0,
                token_estimate=0,
                context_token_estimate=0,
                draft_token_estimate=0,
                llm_call_estimate=0,
                crypto_ops=0,
            )
            apply_tool_guard = False
        else:
            selector_method = "SimTopK" if method == "DirectInject" else method
            selection = select_for_method(selector_method, task, memories, candidate_k, final_k)
            selection_memories = selection.memories
            record = selection.record
            apply_tool_guard = selection.apply_tool_guard

        baseline = draft_trace(task, [])
        trace = draft_trace(task, selection_memories, apply_tool_guard=apply_tool_guard)
        checks = check_trace(task, selection_memories, trace, baseline)
        totals["success"] += int(checks["success"])

        selected_useful = {
            memory.id
            for memory in selection_memories
            if _is_clean_useful(task, memory)
        }
        direct_useful = {
            memory.id
            for memory in direct_reference[task.id]
            if _is_clean_useful(task, memory)
        }
        useful_denominator = max(1, len(direct_useful))
        totals["useful_recall"] += len(selected_useful) / useful_denominator
        totals["false_rejection"] += len(direct_useful - selected_useful) / useful_denominator
        totals["tokens"] += float(record.token_estimate)
        totals["draft_calls"] += float(record.llm_call_estimate)
        totals["cand"] += float(record.decrypted_candidate_count)

    n = len(tasks) or 1
    return {
        "Method": method,
        "Tasks": str(len(tasks)),
        "TSR": f"{100.0 * totals['success'] / n:.1f}",
        "UsefulRecall": f"{100.0 * totals['useful_recall'] / n:.1f}",
        "FalseRejection": f"{100.0 * totals['false_rejection'] / n:.1f}",
        "Tokens": f"{totals['tokens'] / n:.2f}",
        "DraftCalls": f"{totals['draft_calls'] / n:.2f}",
        "Cand.": f"{totals['cand'] / n:.2f}",
    }


def _is_clean_useful(task, memory) -> bool:
    return bool(
        memory.tenant == task.tenant
        and memory.freshness == "valid"
        and memory.trust == "trusted"
        and set(memory.utility_tags).intersection(task.expected_utility_tags)
    )


if __name__ == "__main__":
    raise SystemExit(main())
