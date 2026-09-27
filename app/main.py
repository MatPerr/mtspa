import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.optimization.datamodel import ProblemData
from app.optimization.objectives import (
    LOSS_CONFIGS,
    get_loss_configs,
)
from app.optimization.results import ConfigOptimizationResult
from app.optimization.solvers.dp import (
    DynamicProgrammingSolver,
    StateLimitExceededError,
)
from app.optimization.solvers.sa import (
    optimize_for_loss_configs_parallel,
)
from app.schemas import (
    AnnealingHistoryResponse,
    Coordinate,
    GeocodeSuggestion,
    ConfigSolutionResponse,
    LossConfigResponse,
    LossTermResponse,
    SampleDatasetResponse,
    SampleProblemResponse,
    SolveRequest,
    SolveResponse,
    TourResponse,
)
from app.services.geocoding import GeocodingServiceError, search_addresses
from app.services.osrm import RoutingServiceError, get_travel_matrices
from app.services.problem_builder import build_problem, input_coordinates
from app.services.samples import SAMPLES, list_samples, load_sample
from app.services.tour_timeline import build_tour_timeline

app = FastAPI(title="MTSPA API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/loss-configs", response_model=list[LossConfigResponse])
def loss_configs() -> list[LossConfigResponse]:
    """Expose available objectives, importance values, and supported solvers.

    Returns:
        Objective definitions in catalog order. Importance values are not yet
        calibrated against any particular problem.
    """
    return [
        LossConfigResponse(
            id=config.id,
            name=config.name,
            description=config.description,
            supported_solvers=list(config.supported_solvers),
            terms=[
                LossTermResponse(
                    metric=metric.value,
                    importance=importance,
                )
                for metric, importance in config.importances.items()
            ],
        )
        for config in LOSS_CONFIGS.values()
    ]


@app.get("/api/samples", response_model=list[SampleDatasetResponse])
def sample_datasets() -> list[SampleDatasetResponse]:
    return list_samples()


@app.get("/api/sample", response_model=SampleProblemResponse)
def sample_problem(sample_id: str = "belgium") -> SampleProblemResponse:
    """Return editable inputs for a catalogued sample dataset.

    Args:
        sample_id: Catalog identifier, defaulting to the original Belgium sample.

    Returns:
        Sample agents and appointments without saved routing matrices.

    Raises:
        HTTPException: A 404 response if the sample ID is unknown.
    """
    if sample_id not in SAMPLES:
        raise HTTPException(status_code=404, detail="Unknown sample dataset")
    return load_sample(sample_id)


@app.get("/api/geocode", response_model=list[GeocodeSuggestion])
async def geocode(
    query: str = Query(min_length=3, max_length=300),
    limit: int = Query(default=5, ge=1, le=10),
) -> list[GeocodeSuggestion]:
    """Return address suggestions suitable for the problem editor.

    Args:
        query: Address search text, validated by the API to 3-300 characters.
        limit: Maximum number of suggestions, validated by the API to 1-10.

    Returns:
        Suggested labels and geographic coordinates in provider order.

    Raises:
        HTTPException: A 502 response if the geocoding service fails.
    """
    try:
        locations = await search_addresses(query, limit)
    except GeocodingServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return [
        GeocodeSuggestion(
            latitude=location.latitude,
            longitude=location.longitude,
            label=location.label,
        )
        for location in locations
    ]


@app.post("/api/solve", response_model=SolveResponse)
async def solve(request: SolveRequest) -> SolveResponse:
    """Fetch driving costs and solve all requested objectives off the event loop.

    Args:
        request: Validated agents, appointments, objectives, and solver options.

    Returns:
        Solutions with routes, metrics, and display timelines. Reported elapsed
        time covers solver execution and excludes the routing request.

    Raises:
        HTTPException: A 502 response for routing-service failures, or a 422
            response for solver validation, infeasibility, or state-limit errors.
    """
    coordinates = input_coordinates(request.agents, request.appointments)
    try:
        distances, travel_times = await get_travel_matrices(coordinates)
    except RoutingServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    problem = build_problem(
        request.agents,
        request.appointments,
        distances,
        travel_times,
    )
    started = time.perf_counter()
    try:
        config_results, final_state_count = await asyncio.to_thread(
            _run_solver,
            problem,
            request,
        )
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return _solve_response(
        request.solver,
        problem,
        config_results,
        time.perf_counter() - started,
        final_state_count,
    )


@app.post("/api/solve-stream")
async def solve_stream(request: SolveRequest) -> StreamingResponse:
    """Fetch driving costs and open a newline-delimited solver event stream.

    Args:
        request: Validated agents, appointments, objectives, and solver options.

    Returns:
        A streaming response containing progress events followed by a result
        or solver-error event. Routing completes before streaming begins.

    Raises:
        HTTPException: A 502 response if the routing service fails.
    """
    coordinates = input_coordinates(request.agents, request.appointments)
    try:
        distances, travel_times = await get_travel_matrices(coordinates)
    except RoutingServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    problem = build_problem(
        request.agents,
        request.appointments,
        distances,
        travel_times,
    )
    return StreamingResponse(
        _stream_solver(problem, request),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no"},
    )


async def _stream_solver(
    problem: ProblemData,
    request: SolveRequest,
) -> AsyncIterator[str]:
    """Bridge a solver thread's progress and final result into NDJSON events.

    Args:
        problem: Built routing problem with driving matrices.
        request: Validated solver settings and requested objectives.

    Yields:
        JSON objects terminated by newlines: progress events followed by one
        result or recognized solver-error event. SA progress counts steps;
        DP progress reports state usage relative to its limit.
    """
    started = time.perf_counter()
    event_loop = asyncio.get_running_loop()
    progress_events: asyncio.Queue[tuple[int, int]] = asyncio.Queue()

    def report_progress(current: int, total: int) -> None:
        """Enqueue a solver-thread progress update on the async event loop.

        Args:
            current: Completed SA steps or current reported DP state count.
            total: Total SA steps or the configured DP state limit.
        """
        event_loop.call_soon_threadsafe(
            progress_events.put_nowait,
            (current, total),
        )

    solver_task = asyncio.create_task(
        asyncio.to_thread(
            _run_solver,
            problem,
            request,
            report_progress,
        )
    )

    while not solver_task.done() or not progress_events.empty():
        try:
            current, total = await asyncio.wait_for(
                progress_events.get(),
                timeout=0.1,
            )
        except TimeoutError:
            continue
        yield json.dumps(
            {
                "type": "progress",
                "metric": "steps" if request.solver == "sa" else "states",
                "current": current,
                "total": total,
            }
        ) + "\n"

    try:
        config_results, final_state_count = await solver_task
    except StateLimitExceededError as error:
        yield json.dumps(
            {
                "type": "error",
                "code": "state_limit_exceeded",
                "detail": str(error),
            }
        ) + "\n"
        return
    except (RuntimeError, ValueError) as error:
        yield json.dumps(
            {
                "type": "error",
                "code": "optimization_failed",
                "detail": str(error),
            }
        ) + "\n"
        return

    result = _solve_response(
        request.solver,
        problem,
        config_results,
        time.perf_counter() - started,
        final_state_count,
    )
    yield json.dumps(
        {
            "type": "result",
            "result": result.model_dump(mode="json"),
        }
    ) + "\n"


def _run_solver(
    problem: ProblemData,
    request: SolveRequest,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[ConfigOptimizationResult], int | None]:
    """Dispatch a synchronous optimization request to DP or parallel SA.

    Args:
        problem: Routing problem ready for optimization.
        request: Solver selection, objectives, and search settings.
        progress_callback: Optional callback receiving current and total steps
            for SA, or state count and state limit for DP.

    Returns:
        Results in requested objective order and the final DP layer's state
        count. The state count is None for SA.

    Raises:
        ValueError: Solver options are invalid or DP finds no feasible solution.
        StateLimitExceededError: DP would exceed the configured state limit.
    """
    if request.solver == "dp":
        solver = DynamicProgrammingSolver(
            problem,
            max_states=request.max_states,
            loss_configs=get_loss_configs(request.loss_config_ids),
        )
        return (
            solver.optimize_for_loss_configs(
                progress_callback=progress_callback,
            ),
            solver.final_state_count,
        )

    return (
        optimize_for_loss_configs_parallel(
            problem,
            tuple(get_loss_configs(request.loss_config_ids)),
            request.steps,
            request.runs,
            seed=request.seed,
            show_progress=False,
            progress_callback=progress_callback,
            record_history=True,
        ),
        None,
    )


def _solve_response(
    solver_name: str,
    problem: ProblemData,
    config_results: list[ConfigOptimizationResult],
    elapsed_seconds: float,
    final_state_count: int | None,
) -> SolveResponse:
    """Convert solver results into API routes, metrics, and display timelines.

    Args:
        solver_name: Solver identifier, either sa or dp.
        problem: Routing data used to label agents and locate nodes.
        config_results: Evaluated solutions paired with objective definitions.
        elapsed_seconds: Solver runtime to report, excluding routing requests.
        final_state_count: Final DP layer size, or None for SA.

    Returns:
        Serializable response with appointment display IDs numbered from one,
        route coordinates, and a timeline for each agent.
    """
    appointment_id_by_node = {
        node_id: appointment_id
        for appointment_id, node_id in enumerate(
            problem.appointment_ids,
            start=1,
        )
    }
    return SolveResponse(
        solver=solver_name,
        elapsed_seconds=elapsed_seconds,
        solutions=[
            ConfigSolutionResponse(
                loss_config_id=result.config.id,
                loss_config_name=result.config.name,
                loss=result.solution.loss,
                metrics=asdict(result.solution.metrics),
                tours=[
                    TourResponse(
                        agent_id=agent_id,
                        agent_name=problem.agents[agent_id].name,
                        node_ids=tour,
                        appointment_ids=[
                            appointment_id_by_node[node_id]
                            for node_id in tour[1:-1]
                        ],
                        coordinates=[
                            Coordinate(
                                latitude=problem.nodes[node_id].latitude,
                                longitude=problem.nodes[node_id].longitude,
                            )
                            for node_id in tour
                        ],
                        metrics=asdict(tour_metrics),
                        timeline=build_tour_timeline(problem, agent_id, tour, appointment_id_by_node),
                    )
                    for agent_id, (tour, tour_metrics) in enumerate(
                        zip(
                            result.solution.tours,
                            result.solution.tour_metrics,
                            strict=True,
                        )
                    )
                ],
                final_state_count=final_state_count,
                annealing_history=(
                    AnnealingHistoryResponse.model_validate(asdict(result.annealing_history))
                    if result.annealing_history is not None
                    else None
                ),
            )
            for result in config_results
        ],
    )
