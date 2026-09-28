# sa.py — simulated annealing with app and reporting support

[Documentation index](README.md)

Source: [sa.py](../app/optimization/solvers/sa.py).
Run from the repository root: `uv run python -m app.optimization.solvers.sa`.

Read each tree top to bottom. Indentation shows calls; `[brackets]` mark
conditions, loops, or inline work. Alternative branches do not all execute.
The search is the same as [SA lite](sa_lite.md); the extra layers handle
multiple objectives, progress, loss history, and exported reports.

## CLI entry point

```text
main()
├── [parse filepath, steps, runs, seed, loss config, output directory]
├── load_data(filepath)
├── ProblemData(...)
│   └── __post_init__()
├── SimulatedAnnealingSolver(...)
│   └── __init__()
│       ├── random.Random(seed)
│       └── calibrate_loss_weights()     once; skipped if weights are supplied
├── [start runtime timer]
├── [runs == 1] optimize(steps)
├── [runs > 1] optimize_parallel(steps, n_runs)
│   └── optimize_for_loss_configs_parallel()  one config, already-calibrated weights
├── [stop runtime timer]
├── save_solution_report()
│   ├── _summary_data()
│   │   └── _tour_data()                 per agent; JSON also includes nodes
│   └── _render_svg()
│       └── _tour_lines()                route text and metrics
└── [print metrics, routes, and JSON/SVG paths]
```

The CLI selects one loss config. Multiple configs and convergence history are
available through the Python/app entry point below, not through extra CLI runs
hidden inside `main()`.

## App / multi-config entry point

The app calls the module-level function directly, bypassing `main()` and the
single-config `optimize_parallel()` wrapper.

```text
app.main._run_solver()                   SA branch; requests loss history
└── optimize_for_loss_configs_parallel(problem, configs, steps, n_runs, ...)
    ├── [validate inputs]
    ├── [weights not supplied] calibrate_loss_weights_for_configs()
    │   ├── estimate_metric_scales()     one shared calibration walk
    │   └── calibrate_loss_weights(scales=...) for each config
    ├── [generate run seeds; reuse the same seed sequence across configs]
    ├── SimulatedAnnealingSolver(..., weights=...) for each (config, run)
    ├── [one job] _optimize_run()        directly; no process pool
    ├── [multiple jobs, no progress callback]
    │   ├── ProcessPoolExecutor.submit(_optimize_run, ...) for each job
    │   └── as_completed(...) + tqdm     collect results by config
    ├── [multiple jobs, progress callback supplied]
    │   └── _run_config_jobs_with_progress()   expanded below
    └── min(..., key=result.solution.loss) for each config
        └── [return list[ConfigOptimizationResult] in config order]
```

Worker entry and optional history:

```text
_optimize_run(solver, ..., record_history)
├── [create history-points list]
├── solver.optimize(..., history_callback=points.append if requested)
├── [if requested] AnnealingHistory(run_number, run_count, points)
└── ConfigOptimizationResult(config, best_solution, history)
```

The winning solution keeps its own run's history, not a mixture of all runs.
The app builds its response separately; it does not call the CLI's report writer.

## One optimization run

```text
optimize(steps)
├── initialize_solution()
│   ├── initialize_random_tours()
│   └── build_solution(tours)            full initial metrics
├── [optional] history_callback(AnnealingHistoryPoint(0, current.loss, best.loss))
├── calibrate_temperature()
│   ├── estimate_typical_delta()
│   │   └── [sample neighbors of the fixed initial solution]
│   │       ├── sample_neighbor()
│   │       ├── [if a move exists] calculate_metrics(..., cached metrics, changed IDs)
│   │       └── [if a move exists] calculate_loss()
│   └── TemperatureCalibration(...)
├── [for each step, wrapped in optional tqdm]
│   ├── sample_neighbor(current.tours)
│   │   └── [valid move] swap_appointments() or give_appointment()
│   ├── [if a move exists]
│   │   ├── build_solution(neighbor_tours, previous=current, changed_agent_ids=...)
│   │   └── [accept/reject; update current and best]
│   ├── [terminal progress enabled] progress.set_postfix(losses, temperature)
│   ├── [at integer percentage boundaries, if callbacks supplied]
│   │   ├── progress_callback(completed_steps, total_steps)
│   │   └── history_callback(AnnealingHistoryPoint(...))
│   └── [temperature *= cooling_rate; also happens when no move exists]
└── [return best Solution]

build_solution(tours, previous=None, changed_agent_ids=None)
├── calculate_metrics()
│   ├── [no cache] calculate_tour_metrics() for every agent
│   ├── [cache supplied] copy cached list; calculate_tour_metrics() for changed IDs
│   └── calculate_solution_metrics()
│       └── compute_std()
├── calculate_loss(metrics, weights)
└── Solution(tours, tour_metrics, metrics, loss)
```

Acceptance uses `exp(-loss_change / temperature)` for worsening moves.
History contains at most 101 samples: the initial state plus percentage-boundary
updates. Neither history nor progress changes the RNG draws or acceptance rule.

## Parallel progress communication

Only used when multiple jobs run with a progress callback:

```text
_run_config_jobs_with_progress()         parent process
├── Manager().Queue()                    shared queue for step updates
├── ProcessPoolExecutor()
│   └── submit(_optimize_with_progress, ...) for each job
│       └── _optimize_with_progress()    worker process
│           └── _optimize_run(progress_callback=report_progress)
│               └── solver.optimize()
│                   └── report_progress() at percentage boundaries
│                       └── progress_queue.put((job_id, completed_steps))
├── [while jobs remain]
│   ├── wait(..., FIRST_COMPLETED)       collect finished results
│   ├── progress.update(...)            terminal completed-run bar
│   ├── progress_queue.get_nowait()     drain worker step updates
│   └── [new aggregate percentage] progress_callback(total completed, total planned)
└── [if needed] progress_callback(total_steps, total_steps)
```

The queue carries step counts, not every candidate or metric. Loss-history
points return with each worker's result. `optimize_parallel()` adds an RNG-seed
derivation layer before the shared runner; its worker seeds therefore differ
from the lite wrapper for the same constructor seed.

Shared helper details: [sa_lite.md](sa_lite.md#shared-helper-calls).
App dispatch: [app/main.py](../app/main.py).
Exports: [reporting.py](../app/optimization/reporting.py).
