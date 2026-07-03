from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .planner import draft_trace
from .policy_checker import check_trace
from .schemas import MemoryCapsule, SelectionRecord, Task, ToolTrace, estimate_tokens


METHODS = [
    "SimTopK",
    "Sim+Recency",
    "CapsuleFilter",
    "ToolGuardOnly",
    "PairwiseGate",
    "MemAct-Lite",
    "MemAct-Strict",
]


@dataclass(frozen=True)
class Selection:
    record: SelectionRecord
    memories: list[MemoryCapsule]
    apply_tool_guard: bool = False


@dataclass(frozen=True)
class MemoryActOptions:
    enforce_privacy: bool = True
    enforce_freshness: bool = True
    enforce_usage_policy: bool = True
    action_probe: bool = True
    set_recheck: bool = True
    probe_count: int = 1
    risk_threshold: float = 2.0
    lambda_risk: float = 1.0
    method_name: str = "MemAct"


def select_for_method(
    method: str,
    task: Task,
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
) -> Selection:
    if method == "SimTopK":
        return _simple_select(method, task, memories, candidate_k, final_k, _lexical_score)
    if method == "Sim+Recency":
        return _simple_select(method, task, memories, candidate_k, final_k, _recency_score)
    if method == "CapsuleFilter":
        return _metadata_filter_select(task, memories, candidate_k, final_k)
    if method == "ToolGuardOnly":
        sel = _simple_select(method, task, memories, candidate_k, final_k, _lexical_score)
        return Selection(sel.record, sel.memories, apply_tool_guard=True)
    if method == "PairwiseGate":
        return _pairwise_gate_select(task, memories, candidate_k, final_k)
    if method in {"MemAct", "MemAct-Lite"}:
        return memoryact_select(
            task,
            memories,
            candidate_k,
            final_k,
            MemoryActOptions(probe_count=1, method_name="MemAct-Lite"),
        )
    if method == "MemAct-Strict":
        return memoryact_select(
            task,
            memories,
            candidate_k,
            final_k,
            MemoryActOptions(probe_count=2, method_name="MemAct-Strict"),
        )
    raise ValueError(f"unknown method: {method}")


def select_ablation(
    variant: str,
    task: Task,
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
) -> Selection:
    options = {
        "Full MemAct": MemoryActOptions(),
        "w/o PrivacyFilter": MemoryActOptions(enforce_privacy=False),
        "w/o ActionProbe": MemoryActOptions(action_probe=False, set_recheck=False),
        "w/o UsagePolicy": MemoryActOptions(enforce_usage_policy=False, set_recheck=False),
        "w/o FreshnessCheck": MemoryActOptions(enforce_freshness=False, set_recheck=False),
        "w/o SetRecheck": MemoryActOptions(set_recheck=False),
    }[variant]
    selected = memoryact_select(task, memories, candidate_k, final_k, options)
    return Selection(
        SelectionRecord(
            method=variant,
            selected_memory_ids=selected.record.selected_memory_ids,
            candidate_count=selected.record.candidate_count,
            decrypted_candidate_count=selected.record.decrypted_candidate_count,
            restricted_memory_ids=selected.record.restricted_memory_ids,
            latency_ms=selected.record.latency_ms,
            token_estimate=selected.record.token_estimate,
            context_token_estimate=selected.record.context_token_estimate,
            draft_token_estimate=selected.record.draft_token_estimate,
            llm_call_estimate=selected.record.llm_call_estimate,
            baseline_draft_calls=selected.record.baseline_draft_calls,
            candidate_draft_calls=selected.record.candidate_draft_calls,
            set_draft_calls=selected.record.set_draft_calls,
            crypto_ops=selected.record.crypto_ops,
        ),
        selected.memories,
        selected.apply_tool_guard,
    )


def memoryact_select(
    task: Task,
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
    options: MemoryActOptions,
) -> Selection:
    started = time.perf_counter()
    candidates = _ranked_candidates(task, memories, candidate_k, _lexical_score)
    filtered = [
        memory
        for memory in candidates
        if _privacy_filter(task, memory, options)
    ]
    baseline = draft_trace(task, [])
    scored: list[tuple[float, float, MemoryCapsule]] = []
    token_estimate = estimate_tokens(task.description)
    baseline_draft_calls = 1
    candidate_draft_calls = 0
    set_draft_calls = 0

    for memory in filtered:
        utility = _estimate_utility(task, memory)
        risk = _estimate_metadata_risk(task, memory, options)
        if options.action_probe:
            for probe_round in range(max(1, options.probe_count)):
                probed_trace = draft_trace(task, [memory], probe_round=probe_round)
                check = check_trace(task, [memory], probed_trace, baseline)
                risk += _probe_risk(check, options)
                token_estimate += estimate_tokens(memory.content) + 80
                candidate_draft_calls += 1
        score = utility - options.lambda_risk * risk
        scored.append((score, risk, memory))

    scored.sort(key=lambda item: (-item[0] / max(1, len(item[2].content)), item[2].id))
    selected: list[MemoryCapsule] = []
    restricted: list[str] = []
    for score, risk, memory in scored:
        if len(selected) >= final_k:
            break
        if score <= 0:
            continue
        if options.set_recheck:
            violates, recheck_calls, recheck_tokens = _selected_set_check(
                task,
                selected + [memory],
                options,
                baseline,
            )
            set_draft_calls += recheck_calls
            token_estimate += recheck_tokens
            if violates:
                restricted.append(memory.id)
                continue
        if risk <= options.risk_threshold:
            selected.append(memory)
        elif _estimate_utility(task, memory) > 0:
            restricted.append(memory.id)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    context_token_estimate = sum(estimate_tokens(m.content) for m in selected)
    return Selection(
        SelectionRecord(
            method=options.method_name,
            selected_memory_ids=[m.id for m in selected],
            candidate_count=len(candidates),
            decrypted_candidate_count=len(filtered),
            restricted_memory_ids=restricted,
            latency_ms=elapsed_ms,
            token_estimate=token_estimate,
            context_token_estimate=context_token_estimate,
            draft_token_estimate=token_estimate,
            llm_call_estimate=baseline_draft_calls + candidate_draft_calls + set_draft_calls,
            baseline_draft_calls=baseline_draft_calls,
            candidate_draft_calls=candidate_draft_calls,
            set_draft_calls=set_draft_calls,
            crypto_ops=len(candidates) + len(filtered),
        ),
        selected,
    )


def _pairwise_gate_select(
    task: Task,
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
) -> Selection:
    started = time.perf_counter()
    candidates = _ranked_candidates(task, memories, candidate_k, _lexical_score)
    scored: list[tuple[float, MemoryCapsule]] = []
    for memory in candidates:
        score = _estimate_utility(task, memory)
        if memory.tenant != task.tenant:
            score -= 5.0
        if memory.freshness != "valid":
            score -= 3.0
        if memory.trust == "low":
            score -= 2.0
        if memory.sensitivity in {"sensitive", "secret"}:
            score -= 0.8
        if not set(memory.utility_tags).intersection(task.expected_utility_tags):
            score -= 1.0
        scored.append((score, memory))

    scored.sort(key=lambda item: (-item[0], item[1].id))
    selected = [memory for score, memory in scored if score > 0][:final_k]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    context_token_estimate = sum(estimate_tokens(m.content) for m in selected)
    return Selection(
        SelectionRecord(
            method="PairwiseGate",
            selected_memory_ids=[m.id for m in selected],
            candidate_count=len(candidates),
            decrypted_candidate_count=len(candidates),
            latency_ms=elapsed_ms,
            token_estimate=context_token_estimate,
            context_token_estimate=context_token_estimate,
            draft_token_estimate=0,
            llm_call_estimate=0,
            crypto_ops=len(candidates),
        ),
        selected,
    )


def _selected_set_check(
    task: Task,
    selected: list[MemoryCapsule],
    options: MemoryActOptions,
    baseline: ToolTrace,
) -> tuple[bool, int, int]:
    if not selected:
        return False, 0, 0
    calls = 0
    tokens = 0
    for probe_round in range(max(1, options.probe_count)):
        trace = draft_trace(task, selected, probe_round=probe_round)
        calls += 1
        tokens += sum(estimate_tokens(memory.content) for memory in selected) + 80
        check = check_trace(task, selected, trace, baseline)
        ignored_by_disabled_module = (
            (check["ctmir"] and not options.enforce_privacy)
            or (check["smmr"] and not options.enforce_freshness)
            or (check["pvar"] and not options.enforce_usage_policy)
        )
        if (
            (check["ctmir"] and options.enforce_privacy)
            or (check["smmr"] and options.enforce_freshness)
            or (check["pvar"] and options.enforce_usage_policy)
            or check["utir"]
            or (check["unsafe_miad"] and not ignored_by_disabled_module)
        ):
            return True, calls, tokens
    return False, calls, tokens


def _simple_select(
    method: str,
    task: Task,
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
    scorer,
) -> Selection:
    started = time.perf_counter()
    candidates = _ranked_candidates(task, memories, candidate_k, scorer)
    selected = candidates[:final_k]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    context_token_estimate = sum(estimate_tokens(m.content) for m in selected)
    return Selection(
        SelectionRecord(
            method=method,
            selected_memory_ids=[m.id for m in selected],
            candidate_count=len(candidates),
            decrypted_candidate_count=len(selected),
            latency_ms=elapsed_ms,
            token_estimate=context_token_estimate,
            context_token_estimate=context_token_estimate,
            draft_token_estimate=0,
            llm_call_estimate=0,
            crypto_ops=len(selected),
        ),
        selected,
    )


def _metadata_filter_select(
    task: Task,
    memories: list[MemoryCapsule],
    candidate_k: int,
    final_k: int,
) -> Selection:
    started = time.perf_counter()
    candidates = _ranked_candidates(task, memories, candidate_k, _lexical_score)
    filtered = [
        m
        for m in candidates
        if m.tenant == task.tenant
        and m.freshness == "valid"
        and m.trust == "trusted"
    ]
    selected = filtered[:final_k]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    context_token_estimate = sum(estimate_tokens(m.content) for m in selected)
    return Selection(
        SelectionRecord(
            method="CapsuleFilter",
            selected_memory_ids=[m.id for m in selected],
            candidate_count=len(candidates),
            decrypted_candidate_count=len(filtered),
            latency_ms=elapsed_ms,
            token_estimate=context_token_estimate,
            context_token_estimate=context_token_estimate,
            draft_token_estimate=0,
            llm_call_estimate=0,
            crypto_ops=len(candidates) + len(filtered),
        ),
        selected,
    )


def _ranked_candidates(task: Task, memories: list[MemoryCapsule], k: int, scorer) -> list[MemoryCapsule]:
    scored = [
        (scorer(task, memory), memory)
        for memory in memories
        if memory.scenario == task.scenario
    ]
    scored = [(score, memory) for score, memory in scored if score > 0]
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [memory for _, memory in scored[:k]]


def _lexical_score(task: Task, memory: MemoryCapsule) -> float:
    q = _tokens(task.description)
    c = _tokens(memory.content)
    if not q or not c:
        return 0.0
    overlap = len(q.intersection(c)) / max(1, len(q))
    tag_boost = 0.35 if set(memory.utility_tags).intersection(task.expected_utility_tags) else 0.0
    scenario_boost = 0.20 if memory.scenario == task.scenario else 0.0
    return overlap + tag_boost + scenario_boost


def _recency_score(task: Task, memory: MemoryCapsule) -> float:
    score = _lexical_score(task, memory)
    if memory.freshness == "valid":
        score += 0.25
    else:
        score -= 0.35
    if memory.trust == "low":
        score -= 0.05
    return score


def _tokens(text: str) -> set[str]:
    raw = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {
        token
        for token in raw
        if len(token) > 2 and not token.startswith("tenant")
    }


def _privacy_filter(task: Task, memory: MemoryCapsule, options: MemoryActOptions) -> bool:
    if options.enforce_privacy and memory.tenant != task.tenant:
        return False
    if options.enforce_freshness and memory.freshness != "valid":
        return False
    if memory.trust == "low":
        return False
    if options.enforce_usage_policy:
        if "internal_analysis" not in memory.usage_scope and "draft_only" not in memory.usage_scope:
            return False
        if "cross_tenant_context" in memory.forbidden_sinks and memory.tenant != task.tenant:
            return False
    return True


def _estimate_utility(task: Task, memory: MemoryCapsule) -> float:
    utility = 0.0
    if set(memory.utility_tags).intersection(task.expected_utility_tags):
        utility += 3.0
    if memory.scenario == task.scenario:
        utility += 0.5
    if memory.freshness == "valid":
        utility += 0.3
    if memory.trust == "trusted":
        utility += 0.2
    return utility


def _estimate_metadata_risk(
    task: Task,
    memory: MemoryCapsule,
    options: MemoryActOptions,
) -> float:
    risk = 0.0
    if options.enforce_privacy and memory.tenant != task.tenant:
        risk += 5.0
    if options.enforce_freshness and memory.freshness != "valid":
        risk += 4.0
    if memory.trust == "low":
        risk += 3.0
    if options.enforce_usage_policy and memory.sensitivity in {"sensitive", "secret"}:
        risk += 0.5
    return risk


def _probe_risk(check: dict[str, bool], options: MemoryActOptions) -> float:
    risk = 0.0
    if options.enforce_privacy and check["ctmir"]:
        risk += 5.0
    if options.enforce_freshness and check["smmr"]:
        risk += 4.0
    if options.enforce_usage_policy and check["pvar"]:
        risk += 5.0

    ignored_by_disabled_module = (
        (check["ctmir"] and not options.enforce_privacy)
        or (check["smmr"] and not options.enforce_freshness)
        or (check["pvar"] and not options.enforce_usage_policy)
    )
    if check["utir"] and not ignored_by_disabled_module:
        risk += 4.0
    if check["unsafe_miad"] and not ignored_by_disabled_module:
        risk += 3.0
    return risk
