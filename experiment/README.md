# MemAct Artifact

This directory contains the artifact for the MemAct paper. It includes the benchmark generator, sandboxed typed-tool traces, admission baselines, MemAct/CAMP selectors, metric scripts, reported result tables, and figure-generation code.

## What This Benchmark Tests

Main claim:

> In multi-tenant cloud agents, relevance-based retrieval can improve task completion, but it can also introduce cross-tenant memories, privacy-violating externalization, and memory-induced action drift. MemAct reduces these risks before context injection while preserving task success.

The benchmark is reproducible and instrumented:

- 3 scenarios: Cloud Dev Agent, Cloud Office Agent, Cloud Compliance Agent
- 5 tenants
- 40 tasks per scenario by default, 120 tasks total
- 50 memory capsules per tenant per scenario by default, 750 memories total
- Sandboxed cloud connectors; no production email, repository, or approval system is touched
- Connector calls produce structured JSON tool traces and auditable state transitions

## Optional Project-Code Reuse

The benchmark can optionally reuse an existing `memkernel` CLI through `memoryact_exp/memkernel_adapter.py`. The paper results do not require production accounts, private data, or live enterprise systems.

The adapter automatically looks for:

- `MEMKERNEL_BIN`
- `target/release/memkernel`
- `target/debug/memkernel`

When found, it runs a smoke flow through the CLI:

```text
memkernel init
memkernel add
memkernel index
memkernel select
memkernel inject
```

This optional smoke test keeps the artifact aligned with an engineering memory store while letting the benchmark runner focus on multi-tenant task generation, sandboxed connector traces, MemAct/CAMP selection, and metrics.

## Run

From the repository root:

```bash
python3 experiment/run_benchmark.py --skip-memkernel-smoke
```

Quick smoke run:

```bash
python3 experiment/run_benchmark.py \
  --tasks-per-scenario 4 \
  --memories-per-tenant-scenario 10 \
  --no-ablation \
  --skip-memkernel-smoke
```

Run the sensitivity, stress, and clean-utility tables:

```bash
python3 experiment/run_sensitivity.py
```

Generate the trace-case table:

```bash
python3 experiment/run_trace_cases.py
```

Generate paper figures from the result tables:

```bash
Rscript experiment/figures/make_memoryact_figures.R
```

## Outputs

The runner writes CSV/JSON files to `experiment/results/` by default:

- `table_i_benchmark_stats.csv`
- `table_ii_main_results.csv`
- `table_iii_scenario_results.csv`
- `table_iv_ablation.csv`
- `table_v_overhead.csv`
- `table_vi_candidate_sensitivity.csv`
- `per_task_results.jsonl`
- `tasks.json`
- `memories.json`

The CSV tables are shaped to match the experiment section in the paper.

## Baselines

- `SimTopK`: relevance-only retrieval
- `Sim+Recency`: relevance plus freshness
- `CapsuleFilter`: tenant/source/freshness filtering without action probing
- `ToolGuardOnly`: injects memories first, then blocks unsafe tool calls
- `MemAct`: policy filtering, CAMP action probing, and risk-constrained selection

## Metrics

- `TSR`: task success rate
- `PCSR`: policy-compliant success rate
- `MIAD`: memory-induced action drift
- `Unsafe MIAD`: action drift that crosses a policy boundary
- `CTMIR`: cross-tenant memory injection rate
- `PVAR`: privacy-violating action rate
- `UTIR`: unauthorized tool invocation rate
- `SMMR`: stale memory misuse rate
- `DCC`: decrypted candidate count

## Dependencies

The Python benchmark uses the standard library only. The figure script requires R packages `ggplot2`, `patchwork`, `jsonlite`, `svglite`, and `ragg`.

## Privacy and Data

The artifact uses synthetic tenants, tasks, memories, and connector states. It does not contain production emails, repositories, payment records, credentials, API keys, or private tenant data.
