from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoryCapsule:
    id: str
    tenant: str
    scenario: str
    domain: str
    source: str
    timestamp: str
    freshness: str
    sensitivity: str
    usage_scope: list[str]
    forbidden_sinks: list[str]
    content: str
    label: str
    risk_tags: list[str] = field(default_factory=list)
    utility_tags: list[str] = field(default_factory=list)
    trust: str = "trusted"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionBoundary:
    tenant: str
    scenario: str
    allowed_effects: list[str]
    forbidden_effects: list[str]
    confirmation_required_effects: list[str]
    allowed_objects: list[str]
    allowed_sinks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Task:
    id: str
    tenant: str
    scenario: str
    description: str
    boundary: ActionBoundary
    expected_utility_tags: list[str]
    expected_steps: list[str]
    risk_focus: str

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["boundary"] = self.boundary.to_dict()
        return out


@dataclass(frozen=True)
class ToolStep:
    tool: str
    effect: str
    object: str
    tenant: str
    source_memories: list[str]
    sink: str
    requires_confirmation: bool = False
    blocked_by_guard: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolTrace:
    steps: list[ToolStep]

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [step.to_dict() for step in self.steps]}

    @property
    def effects(self) -> list[str]:
        return [step.effect for step in self.steps]

    @property
    def tools(self) -> list[str]:
        return [step.tool for step in self.steps]


@dataclass(frozen=True)
class SelectionRecord:
    method: str
    selected_memory_ids: list[str]
    candidate_count: int
    decrypted_candidate_count: int
    restricted_memory_ids: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    token_estimate: int = 0
    context_token_estimate: int = 0
    draft_token_estimate: int = 0
    llm_call_estimate: int = 0
    baseline_draft_calls: int = 0
    candidate_draft_calls: int = 0
    set_draft_calls: int = 0
    crypto_ops: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    scenario: str
    tenant: str
    method: str
    success: bool
    policy_compliant: bool
    miad: bool
    unsafe_miad: bool
    unsafe_plan: bool
    unsafe_executed_effect: bool
    ctmir: bool
    pvar: bool
    utir: bool
    smmr: bool
    guard_blocked: bool
    selected_memory_ids: list[str]
    trace: dict[str, Any]
    selection: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) + len(text) // 16)
