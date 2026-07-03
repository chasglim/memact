# MemAct Artifact

This repository contains the reproducibility artifact for the MemAct paper:
benchmark generation, sandboxed typed-tool traces, admission baselines,
MemAct/CAMP selectors, deterministic policy checkers, result tables, and figure
scripts.

The artifact uses synthetic tenants, tasks, memories, and connector states. It
does not include production emails, repositories, payment records, credentials,
API keys, or private tenant data.

## Layout

- `experiment/run_benchmark.py`: main benchmark runner.
- `experiment/run_sensitivity.py`: candidate-budget, probe-count, stress-set,
  and clean-utility experiments.
- `experiment/run_trace_cases.py`: trace-level case-study table.
- `experiment/memoryact_exp/`: benchmark, selector, planner, and metric modules.
- `experiment/results/`: result files used by the paper tables and figures.
- `experiment/figures/make_memoryact_figures.R`: figure-generation script.

## Quick Start

The Python benchmark uses the standard library only.

```bash
python3 experiment/run_benchmark.py --skip-memkernel-smoke
python3 experiment/run_sensitivity.py
python3 experiment/run_trace_cases.py
```

To generate figures from the result tables, install the R packages `ggplot2`,
`patchwork`, `jsonlite`, `svglite`, and `ragg`, then run:

```bash
Rscript experiment/figures/make_memoryact_figures.R
```

See `experiment/README.md` for details.
