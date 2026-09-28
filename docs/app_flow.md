# API and frontend integration flow

[Documentation index](README.md)

Sources: [app/main.py](../app/main.py), [schemas.py](../app/schemas.py).

The frontend sends editable agents, appointments, and solver options. The
backend is stateless: each solve builds a fresh `ProblemData`. Solvers remain
synchronous Python code; the API coordinates network I/O and result delivery.

## Standard request

```text
POST /api/solve
└── solve(SolveRequest)
    ├── [request schemas validate values and compatible solver/config choices]
    ├── input_coordinates()
    ├── await get_travel_matrices()      OSRM driving costs
    ├── build_problem() → ProblemData
    ├── [start solver runtime timer]
    ├── await asyncio.to_thread(_run_solver, ...)
    │   └── _run_solver()
    │       ├── [DP] DynamicProgrammingSolver(...).optimize_for_loss_configs()
    │       └── [SA] optimize_for_loss_configs_parallel(..., record_history=True)
    └── _solve_response() → SolveResponse
```

The API dispatches to the full solvers, not the lite modules or their `main()`
functions. See [full SA](sa.md) and [full DP](dp.md) for their call trees.
`asyncio.to_thread()` keeps the solve off the async event-loop thread; it does
not turn the CPU-heavy search into asynchronous optimization. SA's worker pool
provides process-level parallelism for multiple runs/configs.

## Streaming request

```text
POST /api/solve-stream
└── solve_stream(SolveRequest)
    ├── input_coordinates()
    ├── await get_travel_matrices()      completes before streaming starts
    ├── build_problem()
    └── StreamingResponse(_stream_solver(...))
        └── _stream_solver()
            ├── [create asyncio progress queue]
            ├── asyncio.create_task(asyncio.to_thread(_run_solver, ..., report_progress))
            │   └── report_progress(current, total) from the solver thread
            │       └── event_loop.call_soon_threadsafe(queue.put_nowait, ...)
            ├── [yield queued progress as newline-delimited JSON]
            └── [when solver finishes]
                ├── [success] _solve_response() → result event
                └── [recognized failure] error event
```

For SA, progress means completed steps across all requested jobs. Its process
queue is separate from this API's asyncio queue: worker updates first reach the
parent solver thread, then this bridge reaches the event loop.
For DP, progress means reported state count relative to the state cap, not
percent complete or measured RAM usage.

## Errors and timing

The standard endpoint maps routing-service errors to HTTP 502 and recognized
solver errors to HTTP 422. Request-schema failures also receive validation
errors. The streaming endpoint handles routing before opening the stream;
recognized solver failures become `type: "error"` events. DP state-budget
failure uses `code: "state_limit_exceeded"`, not an infeasibility claim.

API solver runtime starts after matrices and `ProblemData` are ready. It
includes solver construction/loss calibration inside `_run_solver`, unlike
CLI timing, which starts after construction. Neither includes the OSRM request.
The API reports solver results through response models; it does not write CLI
JSON/SVG files. See [reporting](reporting.md) for timelines and ID conversion.

## Other endpoints

- `/api/loss-configs`: config names, metric importances, and supported solvers.
- `/api/samples`: bundled sample catalog and counts.
- `/api/sample`: editable sample inputs; saved matrices are omitted.
- `/api/geocode`: labeled Photon address suggestions.

The data-service steps and provider settings are explained in
[data loading](data_loading.md). Browser rendering and interaction state live
in [frontend/](../frontend/); they do not implement the optimization algorithms.
