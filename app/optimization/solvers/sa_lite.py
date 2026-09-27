"""Simulated annealing without application or progress-reporting concerns."""

import math
import random
from concurrent.futures import ProcessPoolExecutor

from app.optimization.datamodel import AgentId, ProblemData, Solution, Tours
from app.optimization.loss_calibration import resolve_loss_config
from app.optimization.metrics import (
    calculate_solution_metrics,
    calculate_tour_metrics,
    evaluate_neighbor_metrics,
)
from app.optimization.objectives import (
    DEFAULT_LOSS_CONFIG,
    AnyLossConfig,
    calculate_loss,
)
from app.optimization.temperature_calibration import calibrate_temperature
from app.optimization.variation_ops import initialize_random_tours, sample_neighbor


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
            metrics = calculate_solution_metrics(metrics_by_tour)
        else:
            if changed_agent_ids is None:
                raise ValueError(
                    "changed_agent_ids is required with a previous solution"
                )
            metrics_by_tour, metrics = evaluate_neighbor_metrics(
                self.problem,
                tours,
                previous_metrics=previous.tour_metrics,
                changed_agent_ids=changed_agent_ids,
            )

        return Solution(
            tours=tours,
            tour_metrics=metrics_by_tour,
            metrics=metrics,
            loss=calculate_loss(metrics, self.loss_config),
        )

    def optimize(self, steps: int) -> Solution:
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

        for _ in range(steps):
            neighbor = sample_neighbor(
                self.problem,
                self.rng,
                current.tours,
            )
            if neighbor is None:
                temperature *= temperature_config.cooling_rate
                continue

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

            temperature *= temperature_config.cooling_rate

        return best

    def optimize_parallel(self, steps: int, n_runs: int) -> Solution:
        if steps <= 0:
            raise ValueError("steps must be positive")
        if n_runs <= 0:
            raise ValueError("n_runs must be positive")

        solvers = [
            SimulatedAnnealingSolver(
                self.problem,
                seed=self.rng.getrandbits(64),
                loss_config=self.loss_config,
            )
            for _ in range(n_runs)
        ]
        with ProcessPoolExecutor() as executor:
            futures = [
                executor.submit(solver.optimize, steps)
                for solver in solvers
            ]
            solutions = [future.result() for future in futures]

        return min(solutions, key=lambda solution: solution.loss)
