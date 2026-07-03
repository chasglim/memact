from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .dataset import SCENARIOS
from .schemas import MemoryCapsule, Task, TrialResult


RATE_FIELDS = [
    "TSR",
    "PCSR",
    "MIAD",
    "Unsafe MIAD",
    "UnsafePlan",
    "UnsafeExec",
    "CTMIR",
    "PVAR",
    "UTIR",
    "SMMR",
    "GuardBlocked",
]


def benchmark_stats(tasks: list[Task], memories: list[MemoryCapsule]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        scenario_tasks = [task for task in tasks if task.scenario == scenario]
        scenario_memories = [m for m in memories if m.scenario == scenario]
        risk_types = sorted({tag for m in scenario_memories for tag in m.risk_tags})
        rows.append(
            {
                "Scenario": scenario,
                "Tenants": len({task.tenant for task in scenario_tasks}),
                "Tasks": len(scenario_tasks),
                "Memories": len(scenario_memories),
                "Tools": len(SCENARIOS[scenario]["tools"]),
                "Risk Types": ", ".join(risk_types),
            }
        )
    rows.append(
        {
            "Scenario": "Total",
            "Tenants": len({task.tenant for task in tasks}),
            "Tasks": len(tasks),
            "Memories": len(memories),
            "Tools": sum(len(spec["tools"]) for spec in SCENARIOS.values()),
            "Risk Types": "cross_tenant, stale, privacy, poisoned, unsafe_action",
        }
    )
    return rows


def aggregate_by_method(results: list[TrialResult]) -> list[dict[str, Any]]:
    grouped: dict[str, list[TrialResult]] = defaultdict(list)
    for result in results:
        grouped[result.method].append(result)
    return [_aggregate_row(method, rows) for method, rows in grouped.items()]


def aggregate_by_scenario_method(results: list[TrialResult]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[TrialResult]] = defaultdict(list)
    for result in results:
        grouped[(result.scenario, result.method)].append(result)
    rows = []
    for (scenario, method), values in grouped.items():
        row = _aggregate_row(method, values)
        row["Scenario"] = scenario
        rows.append(row)
    return sorted(rows, key=lambda r: (r["Scenario"], r["Method"]))


def aggregate_overhead(results: list[TrialResult]) -> list[dict[str, Any]]:
    grouped: dict[str, list[TrialResult]] = defaultdict(list)
    for result in results:
        grouped[result.method].append(result)

    rows = []
    for method, values in grouped.items():
        n = len(values) or 1
        selections = [v.selection for v in values]
        rows.append(
            {
                "Method": method,
                "Core ms": _avg(s["latency_ms"] for s in selections),
                "Ctx. Tok.": _avg(s.get("context_token_estimate", s["token_estimate"]) for s in selections),
                "Draft Tok.": _avg(s.get("draft_token_estimate", 0) for s in selections),
                "Base Draft": _avg(s.get("baseline_draft_calls", 0) for s in selections),
                "Cand. Draft": _avg(s.get("candidate_draft_calls", 0) for s in selections),
                "Set Draft": _avg(s.get("set_draft_calls", 0) for s in selections),
                "Total Draft": _avg(s["llm_call_estimate"] for s in selections),
                "Cand.": _avg(s["decrypted_candidate_count"] for s in selections),
                "Tasks": n,
            }
        )
    return rows


def write_reports(
    output_dir: Path,
    tasks: list[Task],
    memories: list[MemoryCapsule],
    main_results: list[TrialResult],
    ablation_results: list[TrialResult],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "table_i_benchmark_stats.csv", benchmark_stats(tasks, memories))
    _write_csv(output_dir / "table_ii_main_results.csv", aggregate_by_method(main_results))
    _write_csv(output_dir / "table_iii_scenario_results.csv", aggregate_by_scenario_method(main_results))
    _write_csv(output_dir / "table_iv_ablation.csv", aggregate_by_method(ablation_results))
    _write_csv(output_dir / "table_v_overhead.csv", aggregate_overhead(main_results))
    _write_jsonl(output_dir / "per_task_results.jsonl", main_results + ablation_results)
    _write_dataset(output_dir, tasks, memories)


def _aggregate_row(method: str, values: list[TrialResult]) -> dict[str, Any]:
    n = len(values) or 1
    pcsr = sum(1 for r in values if r.success and r.policy_compliant) / n
    row = {
        "Method": method,
        "Tasks": len(values),
        "TSR": sum(r.success for r in values) / n,
        "PCSR": pcsr,
        "MIAD": sum(r.miad for r in values) / n,
        "Unsafe MIAD": sum(r.unsafe_miad for r in values) / n,
        "UnsafePlan": sum(r.unsafe_plan for r in values) / n,
        "UnsafeExec": sum(r.unsafe_executed_effect for r in values) / n,
        "CTMIR": sum(r.ctmir for r in values) / n,
        "PVAR": sum(r.pvar for r in values) / n,
        "UTIR": sum(r.utir for r in values) / n,
        "SMMR": sum(r.smmr for r in values) / n,
        "GuardBlocked": sum(r.guard_blocked for r in values) / n,
    }
    return {key: _fmt_rate(value) if key in RATE_FIELDS else value for key, value in row.items()}


def _fmt_rate(value: float) -> str:
    return f"{100.0 * value:.1f}"


def _avg(values) -> str:
    values = list(values)
    if not values:
        return "0.0"
    return f"{sum(float(v) for v in values) / len(values):.2f}"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_jsonl(path: Path, results: list[TrialResult]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")


def _write_dataset(output_dir: Path, tasks: list[Task], memories: list[MemoryCapsule]) -> None:
    (output_dir / "tasks.json").write_text(
        json.dumps([task.to_dict() for task in tasks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "memories.json").write_text(
        json.dumps([memory.to_dict() for memory in memories], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def print_main_summary(rows: list[dict[str, Any]]) -> str:
    order = ["Method", "TSR", "PCSR", "Unsafe MIAD", "CTMIR", "PVAR", "UTIR"]
    widths = {key: max(len(key), *(len(str(row.get(key, ""))) for row in rows)) for key in order}
    lines = ["  ".join(key.ljust(widths[key]) for key in order)]
    lines.append("  ".join("-" * widths[key] for key in order))
    for row in rows:
        lines.append("  ".join(str(row.get(key, "")).ljust(widths[key]) for key in order))
    return "\n".join(lines)


def label_counts(memories: list[MemoryCapsule]) -> dict[str, int]:
    return dict(Counter(memory.label for memory in memories))
