import argparse
import math
import random
import time
from collections.abc import Callable
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    as_completed,
    wait,
)
from multiprocessing import Manager
from pathlib import Path
from queue import Empty
from typing import Protocol

from app.optimization.datamodel import AgentId, ProblemData, Solution, Tours
from app.optimization.loss_calibration import (
    resolve_loss_config,
    resolve_loss_configs,
)
from app.optimization.metrics import (
    calculate_solution_metrics,
    calculate_tour_metrics,
)
from app.optimization.objectives import (
    DEFAULT_LOSS_CONFIG,
    LOSS_CONFIGS,
    AnyLossConfig,
    calculate_loss,
)
from app.optimization.problem_io import load_data
from app.optimization.results import ConfigOptimizationResult
from app.optimization.temperature_calibration import calibrate_temperature
from app.optimization.variation_ops import initialize_random_tours, sample_neighbor
from tqdm import tqdm


type ProgressCallback = Callable[[int, int], None]


class ProgressQueue(Protocol):
    def put(self, item: tuple[int, int]) -> None: ...

    def get_nowait(self) -> tuple[int, int]: ...


def _optimize_with_progress(
    solver: "SimulatedAnnealingSolver",
    steps: int,
    job_id: int,
    progress_queue: ProgressQueue,
) -> Solution:
    def report_progress(completed_steps: int, _: int) -> None:
        progress_queue.put((job_id, completed_steps))

    return solver.optimize(
        steps,
        show_progress=False,
        progress_callback=report_progress,
    )


class SimulatedAnnealingSolver:
    def __init__(
        self,
        problem: ProblemData,
        seed: int | None = None,
        loss_config: AnyLossConfig = DEFAULT_LOSS_CONFIG,
    ) -> None:
        self.problem = problem
        self.rng = random.Random(seed)
        self.loss_config = resolve_loss_config(problem, loss_config)

    def initialize_solution(self) -> Solution:
        tours = initialize_random_tours(self.problem, self.rng)
        return self.evaluate_tours(tours)

    def evaluate_tours(
        self,
        tours: Tours,
        *,
        previous: Solution | None = None,
        changed_agent_ids: tuple[AgentId, ...] | None = None,
    ) -> Solution:
        if previous is None:
            if changed_agent_ids is not None:
                raise ValueError(
                    "changed_agent_ids requires a previous solution"
                )
            metrics_by_tour = [
                calculate_tour_metrics(self.problem, agent_id, tour)
                for agent_id, tour in enumerate(tours)
            ]
        else:
            if changed_agent_ids is None:
                raise ValueError(
                    "changed_agent_ids is required with a previous solution"
                )
            metrics_by_tour = previous.tour_metrics.copy()

            for agent_id in changed_agent_ids:
                metrics_by_tour[agent_id] = calculate_tour_metrics(
                    self.problem,
                    agent_id,
                    tours[agent_id],
                )

        metrics = calculate_solution_metrics(metrics_by_tour)

        return Solution(
            tours=tours,
            tour_metrics=metrics_by_tour,
            metrics=metrics,
            loss=calculate_loss(metrics, self.loss_config),
        )

    def optimize(
        self,
        steps: int,
        *,
        show_progress: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> Solution:
        if steps <= 0:
            raise ValueError("steps must be positive")

        current = self.initialize_solution()
        best = current

        temperature_config = calibrate_temperature(
            self.problem,
            self.rng,
            current,
            self.loss_config,
            steps,
        )
        temperature = temperature_config.initial_temperature

        progress = tqdm(
            range(steps),
            desc="Simulated annealing",
            unit="step",
            disable=not show_progress,
        )
        last_reported_percent = 0
        for step in progress:
            neighbor = sample_neighbor(
                self.problem,
                self.rng,
                current.tours,
            )
            if neighbor is not None:
                neighbor_tours, changed_agent_ids = neighbor
                candidate = self.evaluate_tours(
                    neighbor_tours,
                    previous=current,
                    changed_agent_ids=changed_agent_ids,
                )
                delta = candidate.loss - current.loss

                if delta <= 0 or self.rng.random() < math.exp(-delta / temperature):
                    current = candidate
                    if current.loss < best.loss:
                        best = current

            if show_progress:
                progress.set_postfix(
                    current_loss=f"{current.loss:,.0f}",
                    best_loss=f"{best.loss:,.0f}",
                    temperature=f"{temperature:.2f}",
                    refresh=False,
                )

            completed_steps = step + 1
            completed_percent = completed_steps * 100 // steps
            if (
                progress_callback is not None
                and completed_percent > last_reported_percent
            ):
                progress_callback(completed_steps, steps)
                last_reported_percent = completed_percent

            temperature *= temperature_config.cooling_rate

        return best

    def optimize_parallel(
        self,
        steps: int,
        n_runs: int,
        *,
        show_progress: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> Solution:
        result = optimize_for_loss_configs_parallel(
            self.problem,
            (self.loss_config,),
            steps,
            n_runs,
            seed=self.rng.getrandbits(64),
            show_progress=show_progress,
            progress_callback=progress_callback,
        )
        return result[0].solution


def optimize_for_loss_configs_parallel(
    problem: ProblemData,
    configs: tuple[AnyLossConfig, ...],
    steps: int,
    n_runs: int,
    *,
    seed: int | None = None,
    show_progress: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> list[ConfigOptimizationResult]:
    if steps <= 0:
        raise ValueError("steps must be positive")
    if n_runs <= 0:
        raise ValueError("n_runs must be positive")
    if not configs:
        raise ValueError("At least one loss config is required")

    resolved_configs = resolve_loss_configs(problem, configs)
    master_rng = random.Random(seed)
    run_seeds = [master_rng.getrandbits(64) for _ in range(n_runs)]
    jobs = [
        (
            config_id,
            SimulatedAnnealingSolver(
                problem,
                seed=run_seed,
                loss_config=config,
            ),
        )
        for config_id, config in enumerate(resolved_configs)
        for run_seed in run_seeds
    ]

    if len(jobs) == 1:
        solution = jobs[0][1].optimize(
            steps,
            show_progress=show_progress,
            progress_callback=progress_callback,
        )
        return [ConfigOptimizationResult(resolved_configs[0], solution)]

    solutions_by_config: list[list[Solution]] = [
        [] for _ in resolved_configs
    ]

    if progress_callback is None:
        with ProcessPoolExecutor() as executor:
            future_config_ids = {
                executor.submit(
                    solver.optimize,
                    steps,
                    show_progress=False,
                ): config_id
                for config_id, solver in jobs
            }
            for future in tqdm(
                as_completed(future_config_ids),
                total=len(jobs),
                desc="Simulated annealing runs",
                unit="run",
                disable=not show_progress,
            ):
                config_id = future_config_ids[future]
                solutions_by_config[config_id].append(future.result())
    else:
        _run_config_jobs_with_progress(
            jobs,
            solutions_by_config,
            steps,
            progress_callback,
            show_progress,
        )

    return [
        ConfigOptimizationResult(
            config,
            min(solutions, key=lambda solution: solution.loss),
        )
        for config, solutions in zip(
            resolved_configs,
            solutions_by_config,
            strict=True,
        )
    ]


def _run_config_jobs_with_progress(
    jobs: list[tuple[int, SimulatedAnnealingSolver]],
    solutions_by_config: list[list[Solution]],
    steps: int,
    progress_callback: ProgressCallback,
    show_progress: bool,
) -> None:
    completed_by_job = [0] * len(jobs)
    total_steps = steps * len(jobs)
    last_reported_percent = 0

    with Manager() as manager:
        progress_queue = manager.Queue()
        with ProcessPoolExecutor() as executor:
            future_config_ids = {
                executor.submit(
                    _optimize_with_progress,
                    solver,
                    steps,
                    job_id,
                    progress_queue,
                ): config_id
                for job_id, (config_id, solver) in enumerate(jobs)
            }
            pending = set(future_config_ids)
            progress = tqdm(
                total=len(jobs),
                desc="Simulated annealing runs",
                unit="run",
                disable=not show_progress,
            )

            while pending:
                finished, pending = wait(
                    pending,
                    timeout=0.05,
                    return_when=FIRST_COMPLETED,
                )
                progress.update(len(finished))
                for future in finished:
                    config_id = future_config_ids[future]
                    solutions_by_config[config_id].append(future.result())

                while True:
                    try:
                        job_id, completed_steps = progress_queue.get_nowait()
                    except Empty:
                        break
                    completed_by_job[job_id] = max(
                        completed_by_job[job_id],
                        completed_steps,
                    )
                    aggregate_steps = sum(completed_by_job)
                    completed_percent = aggregate_steps * 100 // total_steps
                    if completed_percent > last_reported_percent:
                        progress_callback(aggregate_steps, total_steps)
                        last_reported_percent = completed_percent

            progress.close()

    if last_reported_percent < 100:
        progress_callback(total_steps, total_steps)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solve the routing problem with simulated annealing"
    )
    parser.add_argument(
        "filepath",
        nargs="?",
        type=Path,
        default=Path("data/data.json"),
    )
    parser.add_argument("--steps", type=int, default=50_000)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--loss-config",
        choices=LOSS_CONFIGS,
        default=DEFAULT_LOSS_CONFIG.id,
    )
    arguments = parser.parse_args()

    problem = ProblemData(*load_data(arguments.filepath))
    solver = SimulatedAnnealingSolver(
        problem,
        seed=arguments.seed,
        loss_config=LOSS_CONFIGS[arguments.loss_config],
    )

    started = time.perf_counter()
    if arguments.runs == 1:
        solution = solver.optimize(
            steps=arguments.steps,
        )
    else:
        solution = solver.optimize_parallel(
            steps=arguments.steps,
            n_runs=arguments.runs,
        )
    elapsed_seconds = time.perf_counter() - started

    print(f"Total distance: {solution.metrics.total_distance / 1000:.3f} km")
    print(f"Distance standard deviation: {solution.metrics.distance_std / 1000:.3f} km")
    print(f"Total travel time: {solution.metrics.total_travel_time / 60:.1f} min")
    print(
        "Travel-time standard deviation: "
        f"{solution.metrics.travel_time_std / 60:.1f} min"
    )
    print(f"Gain standard deviation: {solution.metrics.gain_std:.3f}")
    print(f"Total gain per km: {solution.metrics.total_gain_per_km:.3f}")
    print(f"Gain-per-km standard deviation: {solution.metrics.gain_per_km_std:.3f}")
    print(f"Total gain per hour: {solution.metrics.total_gain_per_hour:.3f}")
    print(f"Gain-per-hour standard deviation: {solution.metrics.gain_per_hour_std:.3f}")
    print(f"Total lateness: {solution.metrics.total_lateness / 60:.1f} min")
    print(f"Total waiting time: {solution.metrics.total_waiting_time / 60:.1f} min")
    print(f"Waiting-time standard deviation: {solution.metrics.waiting_time_std / 60:.1f} min")
    print(f"Total overtime: {solution.metrics.total_overtime / 60:.1f} min")
    print(f"Overtime standard deviation: {solution.metrics.overtime_std / 60:.1f} min")
    print(f"Elapsed: {elapsed_seconds:.3f} s")
    print("Tours:")
    for agent, tour in zip(problem.agents, solution.tours, strict=True):
        route = " -> ".join(map(str, tour))
        print(f"  {agent.name}: {route}")


if __name__ == "__main__":
    main()
