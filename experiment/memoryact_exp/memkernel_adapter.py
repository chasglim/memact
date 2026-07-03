from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MemKernelSmokeResult:
    available: bool
    binary: str | None
    project_dir: str | None
    selected_count: int = 0
    injected_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "binary": self.binary,
            "project_dir": self.project_dir,
            "selected_count": self.selected_count,
            "injected_count": self.injected_count,
            "error": self.error,
        }


def find_memkernel_binary(repo_root: Path, explicit: str | None = None) -> Path | None:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if os.environ.get("MEMKERNEL_BIN"):
        candidates.append(Path(os.environ["MEMKERNEL_BIN"]))
    candidates.extend(
        [
            repo_root / "target" / "release" / "memkernel",
            repo_root / "target" / "debug" / "memkernel",
        ]
    )
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def run_memkernel_smoke(repo_root: Path, explicit_bin: str | None = None) -> MemKernelSmokeResult:
    binary = find_memkernel_binary(repo_root, explicit_bin)
    if binary is None:
        return MemKernelSmokeResult(
            available=False,
            binary=None,
            project_dir=None,
            error="memkernel binary not found; run `cargo build` first or set MEMKERNEL_BIN",
        )

    with tempfile.TemporaryDirectory(prefix="memoryact-memkernel-") as tmp:
        project = Path(tmp)
        try:
            _run(binary, project, ["init"])
            _run(
                binary,
                project,
                [
                    "add",
                    "--type",
                    "project_rule",
                    "--scope",
                    "project",
                    "--title",
                    "Tenant memory capsule smoke rule",
                    "--body-text",
                    "For smoke tests, run cargo test --all before creating a patch draft.",
                    "--sensitivity",
                    "internal",
                    "--confidence",
                    "0.95",
                ],
            )
            _run(binary, project, ["index", "--format", "json"])
            select_out = _run(
                binary,
                project,
                [
                    "select",
                    "--task",
                    "prepare a patch draft and run cargo test --all",
                    "--mode",
                    "lexical",
                    "--max",
                    "5",
                ],
            )
            selected = json.loads(select_out)["selected"]
            selection_file = project / "selection.json"
            selection_file.write_text(select_out, encoding="utf-8")
            inject_out = _run(
                binary,
                project,
                [
                    "inject",
                    "--from-selection",
                    str(selection_file),
                    "--session-id",
                    "memoryact-smoke",
                ],
            )
            injected = json.loads(inject_out)["count"]
            return MemKernelSmokeResult(
                available=True,
                binary=str(binary),
                project_dir=str(project),
                selected_count=len(selected),
                injected_count=injected,
            )
        except Exception as exc:  # pragma: no cover - surfaced in CLI output
            return MemKernelSmokeResult(
                available=False,
                binary=str(binary),
                project_dir=str(project),
                error=str(exc),
            )


def _run(binary: Path, project: Path, args: list[str]) -> str:
    cmd = [
        str(binary),
        "--scope",
        "project",
        "--project",
        str(project),
        *args,
    ]
    completed = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout
