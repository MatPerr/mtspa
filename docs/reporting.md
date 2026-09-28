# Reports, comparisons, and timelines

[Documentation index](README.md)

Optimization produces a `Solution`. Reporting consumes its existing metrics;
it does not change routes or run another optimization.

## CLI reports

Source: [reporting.py](../app/optimization/reporting.py).

```text
full solver main()
├── optimize() / optimize_parallel() → Solution
└── save_solution_report(problem, solution, runtime, output_directory, ...)
    ├── _summary_data()
    │   ├── [serialize solver, objective, weights, metrics, units, and settings]
    │   ├── [serialize nodes keyed by string node ID]
    │   └── _tour_data() for each agent
    │       └── [name, route IDs, appointment count, and cached tour metrics]
    ├── [write <solver>_<config>_summary.json]
    ├── _render_svg()
    │   ├── [project coordinates and draw geographic route segments]
    │   └── _tour_lines() → _format_time()
    └── [write <solver>_<config>_tours.svg; return both paths]
```

Full SA and DP use the same JSON schema. Lite CLIs print console results only.
Report filenames distinguish solver/config pairs; rerunning the same pair in
the same output directory overwrites its two files.

JSON includes the actual objective weights, loss, runtime, run settings,
`timing_feasible`, solution metrics, and per-agent routes/metrics.
Every home/appointment is available at `report["nodes"][str(node_id)]`, including
`latitude`, `longitude`, `kind`, `agent_id`, `time`, `duration`, and `gain`.
This lets a reader map routes without the original dataset. It does not make
the report a reloadable solver input: it does not contain the D/T matrices.

The SVG uses straight geographic connections, not road-following geometry.
Its size grows with the agent panels. It labels the objective/method and
highlights nonzero lateness or overtime. Keep personal reports in ignored
`artifacts/` or another private location; they include coordinates.

## Runtime and feasibility

CLI/report runtime wraps optimization, including reconstruction/final metrics
and all parallel SA runs. It excludes data loading, loss-weight calibration,
and report writing, but includes per-run temperature calibration.
The exported SA solution is the winner, not an aggregate of worker routes.

`timing_feasible` means total lateness and overtime are both zero. It is not a
complete independent validation of appointment coverage or arbitrary business
constraints. A shorter but late SA result does not beat the feasible DP optimum.

## Comparison command

Source: [scripts/compare.py](../scripts/compare.py).

```text
main()
├── load_data() → ProblemData(...)
├── DynamicProgrammingSolver(...).optimize()
├── SimulatedAnnealingSolver(...).optimize() or optimize_parallel()
├── comparison_rows() → format_table() → print()
└── [unless --no-tours] print_tours()
```

This runs DP then SA using the default Shortest distance config and prints a
comparison. It does not write JSON/SVG reports itself.

## App timelines and result objects

Sources: [results.py](../app/optimization/results.py),
[tour_timeline.py](../app/services/tour_timeline.py), and [app/main.py](../app/main.py).

```text
ConfigOptimizationResult(config, solution, optional SA history)
└── _solve_response()
    ├── [map internal appointment node IDs to one-based display IDs]
    └── [for each agent] TourResponse(...)
        └── build_tour_timeline()
            ├── [replay travel, waiting, and service from workday start]
            ├── [add lateness and overtime overlays]
            └── [add availability after an early return]
```

Timelines span workday start through the later of workday end and actual return.
Lateness/overtime overlap activity; adding their durations to activity would
double-count time. Zero-duration appointments retain markers. Timeline replay
happens for final API results, not inside the optimization loop. The API's
display appointment IDs differ from internal node IDs used by CLI reports.
