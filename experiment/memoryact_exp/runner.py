from __future__ import annotations

import json
from pathlib import Path

from .dataset import build_benchmark
from .memkernel_adapter import run_memkernel_smoke
from .metrics import (
    aggregate_by_method,
    print_main_summary,
    write_reports,
)
from .planner import draft_trace
from .policy_checker import check_trace
from .schemas import MemoryCapsule, Task, TrialResult
from .selectors import METHODS, select_ablation, select_for_method


ABLATION_VARIANTS = [
    "Full MemAct",
    "w/o PrivacyFilter",
    "w/o ActionProbe",
    "w/o UsagePolicy",
    "w/o FreshnessCheck",
    "w/o SetRecheck",
]


def run_benchmark(
    repo_root: Path,
    output_dir: Path,
    tasks_per_scenario: int = 40,
    memories_per_tenant_scenario: int = 50,
    candidate_k: int = 20,
    final_k: int = 5,
    run_ablation: bool = True,
    memkernel_bin: str | None = None,
    skip_memkernel_smoke: bool = False,
) -> str:
    tasks, memories = build_benchmark(
        tasks_per_scenario=tasks_per_scenario,
        memories_per_tenant_scenario=memories_per_tenant_scenario,
    )
    main_results = _run_main_methods(tasks, memories, candidate_k, final_k)
    ablation_results = (
        _run_ablation_methods(tasks, memories, candidate_k, final_k)
        if run_ablation
        else []
    )
    write_reports(output_dir, tasks, memories, main_results, ablation_results)

    smoke_result = None
    if not skip_memkernel_smoke:
        smoke_result = run_memkernel_smoke(repo_root, memkernel_bin)
        (output_dir / "memkernel_smoke.json").write_text(
            json.dumps(smoke_result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    summary = print_main_summary(aggregate_by_method(main_results))
    lines = [
        "MemAct benchmark finished.",
        f"Tasks: {len(tasks)} | Memories: {len(memories)}",
        f"Outputs: {output_dir}",
        "",
        summary,
    ]
    if smoke_result is not None:
        if smoke_result.available:
            lines.append(
                f"\nmemkernel reuse smoke: ok "
                f"(selected={smoke_result.selected_count}, injected={smoke_result.injected_count})"
            )
        else:
            lines.append(f"\nmemkernel reuse smoke: skipped/failed ({smoke_result.error})")
    return "\n".join(lines)


def _run_main_methods(
    tasks: list[Task],
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
) -> list[TrialResult]:
    results: list[TrialResult] = []
    for task in tasks:
        for method in METHODS:
            selection = select_for_method(method, task, memories, candidate_k, final_k)
            results.append(_trial_result(task, selection.record.method, selection, candidate_k))
    return results


def _run_ablation_methods(
    tasks: list[Task],
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
) -> list[TrialResult]:
    results: list[TrialResult] = []
    for task in tasks:
        for variant in ABLATION_VARIANTS:
            selection = select_ablation(variant, task, memories, candidate_k, final_k)
            results.append(_trial_result(task, selection.record.method, selection, candidate_k))
    return results


def _trial_result(task: Task, method: str, selection, candidate_k: int) -> TrialResult:
    baseline = draft_trace(task, [])
    trace = draft_trace(
        task,
        selection.memories,
        apply_tool_guard=selection.apply_tool_guard,
    )
    checks = check_trace(task, selection.memories, trace, baseline)
    return TrialResult(
        task_id=task.id,
        scenario=task.scenario,
        tenant=task.tenant,
        method=method,
        success=checks["success"],
        policy_compliant=checks["policy_compliant"],
        miad=checks["miad"],
        unsafe_miad=checks["unsafe_miad"],
        unsafe_plan=checks["unsafe_plan"],
        unsafe_executed_effect=checks["unsafe_executed_effect"],
        ctmir=checks["ctmir"],
        pvar=checks["pvar"],
        utir=checks["utir"],
        smmr=checks["smmr"],
        guard_blocked=checks["guard_blocked"],
        selected_memory_ids=selection.record.selected_memory_ids,
        trace=trace.to_dict(),
        selection=selection.record.to_dict() | {"requested_candidate_k": candidate_k},
    )
