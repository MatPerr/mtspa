# dp.py — dynamic programming with app and reporting support

[Documentation index](README.md)

Source: [dp.py](../app/optimization/solvers/dp.py).
Run from the repository root: `uv run python -m app.optimization.solvers.dp`.

Read each tree top to bottom. Indentation shows calls; `[brackets]` mark
conditions, loops, or inline work, not additional functions.
The recurrence is the same as [DP lite](dp_lite.md); this version tracks one
or two objectives, reports state-budget usage, and supports CLI exports.

## CLI entry point — one objective

```text
main()
├── [parse filepath, max_states, loss config, output directory]
├── load_data(filepath)
├── ProblemData(...)
│   └── __post_init__()                  validate and precompute feasibility tables
├── DynamicProgrammingSolver(..., loss_configs=(selected_config,))
│   └── __init__()
│       ├── [validate state budget and one/two distinct compatible configs]
│       └── calibrate_loss_weights_for_configs()
│           ├── estimate_metric_scales() one shared calibration random walk
│           └── calibrate_loss_weights(scales=...) for each config
├── [start runtime timer]
├── optimize()
│   ├── [require exactly one config]
│   ├── optimize_for_loss_configs()
│   └── [return results[0].solution]
├── [stop runtime timer]
├── save_solution_report()
│   ├── _summary_data()
│   │   └── _tour_data()                 per agent; JSON also includes nodes
│   └── _render_svg()
│       └── _tour_lines()
└── [print metrics, final state count, and JSON/SVG paths]
```

## App entry point — one or two objectives

```text
app.main._run_solver()                   DP branch
├── DynamicProgrammingSolver(..., loss_configs=get_loss_configs(...))
│   └── __init__()                      same setup as above
├── solver.optimize_for_loss_configs(progress_callback=...)
└── [return config results and final_state_count to the app]
```

This bypasses `main()` and `optimize()` so two configs can be requested.
It is one shared traversal, not two runs in parallel: each state stores a
separate best loss and assignment code for each objective. No process pool
or worker queue is used. The app builds its response, not JSON/SVG files.

## Shared-state DP search

```text
optimize_for_loss_configs()
├── [read distance/waiting weights for each objective]
├── sorted(appointment_ids, key=(time, node_id))
├── [initial state = tuple of every agent's home node]
├── [initial record: (loss, code), or (loss_1, code_1, loss_2, code_2)]
├── [optional] progress_callback(initial_state_count, max_states)
├── [start internal search timer]
├── [for each appointment, in chronological order]
│   ├── [create empty next_states]
│   ├── [for each state and possible agent]
│   │   ├── [lookup can_follow; skip if appointment arrival would be late]
│   │   ├── [form next_state; compute distance and waiting increments once]
│   │   ├── [extend loss and assignment code separately for each config]
│   │   └── [merge into next_states]
│   │       ├── [new state] enforce max_states, then insert
│   │       │   └── [optional, at thresholds] progress_callback(state_count, max_states)
│   │       └── [existing state] keep the better record independently per config
│   ├── [no surviving states] raise ValueError
│   ├── [optional, new high-water count] progress_callback(state_count, max_states)
│   └── [states = next_states]
├── [for each final state]
│   ├── [lookup can_return_home; reject if any agent would return late]
│   ├── [sum return-home distance]
│   └── [for each config: add weighted return distance and keep the best record]
├── [no feasible complete assignment] raise ValueError
├── [record final_state_count and internal elapsed_seconds]
├── [for each config's winning record]
│   ├── reconstruct_tours(problem, appointment_ids, assignment_code)
│   │   └── [decode agent assignments; assemble home-to-home routes]
│   ├── build_solution(tours, weights)
│   │   ├── calculate_metrics()          full evaluation, once per result
│   │   │   ├── calculate_tour_metrics() for every agent
│   │   │   └── calculate_solution_metrics()
│   │   │       └── compute_std()
│   │   ├── calculate_loss(metrics, weights)
│   │   └── Solution(...)
│   ├── [assert matching loss, zero lateness, and zero overtime]
│   └── ConfigOptimizationResult(config, solution)
└── [return results in requested config order]
```

The search loop computes distance/waiting increments directly; it does not
build a `Solution` or calculate complete metrics at every transition.
Return-home feasibility is checked after all appointments have been assigned.
State merging may retain different assignment histories for the two configs.

## Progress, timing, and failures

- The callback reports state count versus state cap, not percent complete or
  measured RAM. It is optional; the CLI supplies no callback.
- A new state beyond `max_states` raises `StateLimitExceededError` immediately.
  That means the resource budget was exhausted, not that the problem is infeasible.
- `self.elapsed_seconds` stops before reconstruction. CLI/report runtime wraps
  `optimize()` and therefore includes reconstruction and final metrics.
- Only Shortest distance and Maximum uptime are supported. Their lateness term
  is zero for valid DP results; the recurrence scores distance and waiting.

The calibration random walk happens before DP and does not seed its states.
Its helper calls are shown in [dp_lite.md](dp_lite.md#shared-helper-calls).
App dispatch: [app/main.py](../app/main.py).
Exports: [reporting.py](../app/optimization/reporting.py).
