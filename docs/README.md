# Documentation

These pages explain the current implementation through function-call trees,
data relationships, and short notes. In the trees, indentation shows calls;
`[brackets]` describe inline work, conditions, or loops rather than functions.

## Suggested reading order

1. [Data loading](data_loading.md): how saved or manual inputs become a problem.
2. [Data model](datamodel.md): nodes, agents, tours, solutions, and cached lookups.
3. [Metrics](metrics.md): route simulation and incremental evaluation.
4. [Objectives](objectives.md) and [loss calibration](loss_calibration.md): what is minimized.
5. [Variation operators](variation_ops.md) and [temperature calibration](temperature_calibration.md).
6. [SA lite](sa_lite.md) and [DP lite](dp_lite.md): the algorithms without app plumbing.
7. [Full SA](sa.md) and [full DP](dp.md): parallel jobs, multiple objectives, and callbacks.
8. [Reports and timelines](reporting.md) and [API flow](app_flow.md): how results reach users.

## How the pieces connect

```text
Saved JSON / editable inputs
└── Data loading / problem construction
    └── ProblemData
        ├── LossConfig + loss calibration → fixed weights
        └── Solver
            ├── SA: random tours → temperature calibration → neighbor search
            ├── DP: chronological state expansion → reconstruct winning tours
            └── [shared evaluation] build_solution()
                ├── calculate_metrics() → TourMetrics[] + SolutionMetrics
                ├── calculate_loss() → loss
                └── Solution
                    ├── CLI: console + optional JSON/SVG reports
                    └── API: routes, timelines, metrics, optional SA history
```

SA builds solutions throughout its search. DP builds complete solutions only
after selecting its winning assignment histories. Both use the same metric
definitions; their feasibility rules differ.

## Running the examples

Run module commands from the repository root after `uv sync --locked`:

```bash
uv run python -m app.optimization.solvers.sa_lite data/corsica_nurses.json --seed 0
uv run python -m app.optimization.solvers.dp_lite data/corsica_nurses.json
```

Use `python -m app...`, not a direct path to a solver file, so Python can find
the `app` package. See the [project README](../README.md) for app setup, sample
datasets, full CLI options, and the agent skill.
