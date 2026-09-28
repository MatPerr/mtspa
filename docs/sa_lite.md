# sa_lite.py — minimal simulated annealing

[Documentation index](README.md)

Source: [sa_lite.py](../app/optimization/solvers/sa_lite.py).
Run from the repository root: `uv run python -m app.optimization.solvers.sa_lite`.

Read each tree top to bottom. Indentation shows calls; `[brackets]` mark
conditions, loops, or inline work, not additional functions. Repeated helpers
are expanded separately below.

## CLI entry point

```text
main()
├── [parse filepath, steps, runs, seed, progress options]
├── load_data(filepath)
├── ProblemData(...)
│   └── __post_init__()                   validate and precompute lookups
├── SimulatedAnnealingSolver(...)
│   └── __init__()
│       ├── random.Random(seed)
│       └── calibrate_loss_weights()     once; skipped if weights are supplied
├── [start runtime timer]
├── [runs == 1] optimize(steps)
├── [runs > 1] optimize_parallel(steps, n_runs)
└── [stop timer; print metrics and every agent's route]
```

The CLI uses the default Shortest distance objective. The Python constructor
also accepts another single loss config. Neither path exports JSON/SVG reports.

## One optimization run

```text
optimize(steps)
├── initialize_solution()
│   ├── initialize_random_tours()         random assignments, sorted by time
│   └── build_solution(tours)            calculate all route metrics
├── [current = best = initial solution]
├── calibrate_temperature()
│   ├── estimate_typical_delta()
│   │   └── [sample neighbors of the fixed initial solution]
│   │       ├── sample_neighbor()
│   │       ├── [if a move exists] calculate_metrics(..., cached metrics, changed IDs)
│   │       └── [if a move exists] calculate_loss()
│   └── TemperatureCalibration(...)      initial temperature and cooling rate
├── [for each step, wrapped in optional tqdm]
│   ├── sample_neighbor(current.tours)
│   ├── [no move] cool temperature and continue
│   ├── build_solution(neighbor_tours, previous=current, changed_agent_ids=...)
│   ├── [accept improvement/tie, or with probability exp(-loss_change / temperature)]
│   │   └── [update current; update best if improved]
│   └── [temperature *= cooling_rate]
└── [return best Solution]
```

## Parallel independent runs

```text
optimize_parallel(steps, n_runs)
├── [for each run]
│   ├── self.rng.getrandbits(64)          independent worker seed
│   └── SimulatedAnnealingSolver(..., weights=self.weights)
│       └── __init__()                   reuse weights; no recalibration
├── ProcessPoolExecutor()
│   └── submit(solver.optimize, steps)   one worker job per run
│       └── optimize()                   same single-run flow above; no worker bar
├── as_completed(...) + optional tqdm    count completed runs, not iterations
├── [collect solutions in submission order]
└── min(..., key=solution.loss)          return the best Solution
```

Each run has its own RNG, starting solution, and temperature calibration.
Only the fixed objective weights and problem data are reused. Equal-loss ties
are resolved by submission order.

## Shared helper calls

```text
build_solution(tours, previous=None, changed_agent_ids=None)
├── calculate_metrics()
│   ├── [no cache] calculate_tour_metrics() for every agent
│   ├── [cache supplied] copy cached list; calculate_tour_metrics() for changed IDs
│   └── calculate_solution_metrics()
│       └── compute_std()                cross-tour standard deviations
├── calculate_loss(metrics, weights)
└── Solution(tours, tour_metrics, metrics, loss)

sample_neighbor()
├── [select two agents; copy outer list and the two changed routes]
├── [both nonempty and swap selected] swap_appointments()
├── [otherwise, if a donor exists] give_appointment()
└── [return new tours + changed IDs, or None if no move is possible]

calibrate_loss_weights()
├── estimate_metric_scales()             deterministic calibration random walk
│   ├── initialize_random_tours()
│   ├── calculate_metrics()              full initial evaluation
│   └── [for each sampled move]
│       ├── sample_neighbor()
│       └── [if a move exists] calculate_metrics(..., cached metrics, changed IDs)
└── [convert metric scales and importances into fixed weights]
```

Helpers live in [metrics.py](../app/optimization/metrics.py),
[variation_ops.py](../app/optimization/variation_ops.py),
[loss_calibration.py](../app/optimization/loss_calibration.py), and
[temperature_calibration.py](../app/optimization/temperature_calibration.py).
The shared move operators and metric calculations are the same as in full SA.
