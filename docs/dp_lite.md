# dp_lite.py — minimal dynamic programming

[Documentation index](README.md)

Source: [dp_lite.py](../app/optimization/solvers/dp_lite.py).
Run from the repository root: `uv run python -m app.optimization.solvers.dp_lite`.

Read each tree top to bottom. Indentation shows calls; `[brackets]` mark
conditions, loops, or inline work, not additional functions.

## CLI entry point

```text
main()
├── [parse filepath and max_states]
├── load_data(filepath)
├── ProblemData(...)
│   └── __post_init__()
│       ├── [validate IDs, homes, and matrix shapes]
│       └── [precompute can_follow and can_return_home tables]
├── DynamicProgrammingSolver(...)
│   └── __init__()
│       ├── [validate state budget and the single DP-compatible objective]
│       └── calibrate_loss_weights()     skipped if weights are supplied
├── [start runtime timer]
├── optimize()
│   └── [StateLimitExceededError] main() exits without a solution
└── [on success: stop timer; print metrics, state count, and every route]
```

The CLI uses Shortest distance. The Python constructor also accepts Maximum
uptime, but only one objective at a time. There are no progress callbacks,
worker processes, or JSON/SVG exports.

## The DP search

Most of the algorithm is written directly inside `optimize()`: the state
expansion and pruning below are loops, not separate helper functions.

```text
optimize()
├── sorted(appointment_ids, key=(time, node_id))
├── [initial state = tuple of every agent's home node]
├── [states[state] = (best partial loss, encoded assignment history)]
├── [for each appointment, in chronological order]
│   ├── [create empty next_states]
│   ├── [for each current state]
│   │   └── [for each possible agent]
│   │       ├── [lookup can_follow: skip if arrival would be late]
│   │       ├── [replace that agent's last node to form next_state]
│   │       ├── [add weighted distance + waiting; extend assignment code]
│   │       └── [merge into next_states]
│   │           ├── [new state] enforce max_states, then insert
│   │           └── [existing state] keep the lower-loss record
│   ├── [no surviving states] raise ValueError
│   └── [states = next_states]
├── [for each final state]
│   ├── [lookup can_return_home for every agent; reject late returns]
│   ├── [add weighted return-home distance]
│   └── [retain the lowest-loss complete assignment]
├── [no feasible complete assignment] raise ValueError
├── reconstruct_tours(problem, appointment_ids, assignment_code)
│   ├── [decode agent assignments from the base-agent-count integer]
│   └── [assemble home → ordered appointments → home for each agent]
├── [record final_state_count]
├── build_solution(tours)
├── [assert matching loss, zero lateness, and zero overtime]
└── [return Solution]
```

State expansion enforces on-time appointments; return-home feasibility is
checked at the end. Complete route metrics are computed for the winner, not
for every DP state. The state cap applies to a layer's size, not RAM bytes.

## Shared helper calls

```text
build_solution(tours)
├── calculate_metrics(problem, tours)    no previous-metrics cache needed
│   ├── calculate_tour_metrics()         for every agent
│   └── calculate_solution_metrics()
│       └── compute_std()
├── calculate_loss(metrics, weights)
└── Solution(tours, tour_metrics, metrics, loss)

calibrate_loss_weights()
├── estimate_metric_scales()
│   ├── initialize_random_tours()
│   ├── calculate_metrics()              full initial evaluation
│   └── [deterministic calibration random walk]
│       ├── sample_neighbor()
│       │   └── [valid move] swap_appointments() or give_appointment()
│       └── [if a move exists] calculate_metrics(..., cached metrics, changed IDs)
└── [convert metric scales and importances into fixed weights]
```

The random walk calibrates the objective before the exact DP search; it does
not initialize the DP states or supply a candidate solution to the search.
The DP search has no SA temperature calibration or neighbor sampling.

Helpers live in [loss_calibration.py](../app/optimization/loss_calibration.py),
[metrics.py](../app/optimization/metrics.py),
[variation_ops.py](../app/optimization/variation_ops.py), and
[dp_reconstruction.py](../app/optimization/solvers/dp_reconstruction.py).
