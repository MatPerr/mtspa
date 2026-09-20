import argparse
import math
import random
import statistics
import time
from bisect import insort_right
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from datamodel import AgentId, ProblemData, Solution, Tour, Tours
from metrics import (
    calculate_solution_metrics,
    calculate_tour_metrics,
)
from tqdm import tqdm
from utils import fair_loss, load_data


class SimulatedAnnealingSolver:
    def __init__(
        self,
        problem: ProblemData,
        seed: int | None = None,
    ) -> None:
        self.problem = problem
        self.rng = random.Random(seed)

    def initialize_solution(self) -> Solution:
        problem = self.problem
        agent_count = len(problem.agents)
        appointments_by_agent = [[] for _ in range(agent_count)]

        for appointment_id in problem.appointment_ids:
            agent_id = self.rng.randrange(agent_count)
            appointments_by_agent[agent_id].append(appointment_id)

        tours = []

        for agent_id, appointments in enumerate(appointments_by_agent):
            appointments.sort(key=problem.node_times.__getitem__)
            home = problem.agent_home_nodes[agent_id]
            tours.append([home, *appointments, home])

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
            loss=fair_loss(metrics),
        )

    def give_appointment(self, donor_tour: Tour, receiver_tour: Tour) -> None:
        appointment_index = self.rng.randrange(1, len(donor_tour) - 1)
        appointment = donor_tour.pop(appointment_index)
        node_times = self.problem.node_times
        insort_right(
            receiver_tour,
            appointment,
            lo=1,
            hi=len(receiver_tour) - 1,
            key=lambda node_id: (
                node_times[node_id],
                node_id,
            ),
        )

    def sample_neighbor(
        self,
        tours: Tours,
    ) -> tuple[Tours, tuple[AgentId, AgentId]] | None:
        donor_id, receiver_id = self.rng.sample(
            range(len(tours)),
            k=2,
        )

        if len(tours[donor_id]) <= 2:
            donor_id, receiver_id = receiver_id, donor_id

        if len(tours[donor_id]) <= 2:
            return None

        neighbor = tours.copy()
        neighbor[donor_id] = tours[donor_id].copy()
        neighbor[receiver_id] = tours[receiver_id].copy()
        self.give_appointment(
            neighbor[donor_id],
            neighbor[receiver_id],
        )
        return neighbor, (donor_id, receiver_id)

    def estimate_typical_delta(
        self,
        solution: Solution,
        samples: int,
    ) -> float:
        delta_magnitudes = []

        for _ in range(samples):
            neighbor = self.sample_neighbor(solution.tours)
            if neighbor is None:
                continue

            neighbor_tours, changed_agent_ids = neighbor
            candidate = self.evaluate_tours(
                neighbor_tours,
                previous=solution,
                changed_agent_ids=changed_agent_ids,
            )
            delta = candidate.loss - solution.loss
            if delta != 0:
                delta_magnitudes.append(abs(delta))

        return statistics.median(delta_magnitudes)

    def optimize(
        self,
        steps: int,
        *,
        show_progress: bool = True,
    ) -> Solution:
        if steps <= 0:
            raise ValueError("steps must be positive")

        current = self.initialize_solution()
        best = current

        calibration_samples = min(100, max(1, steps // 10))
        typical_delta = self.estimate_typical_delta(
            current,
            samples=calibration_samples,
        )
        initial_temperature = -typical_delta / math.log(0.8)
        final_temperature = -typical_delta / math.log(0.001)

        progress = tqdm(
            range(steps),
            desc="Simulated annealing",
            unit="step",
            disable=not show_progress,
        )
        for step in progress:
            temperature = initial_temperature * (
                final_temperature / initial_temperature
            ) ** (step / max(steps - 1, 1))

            neighbor = self.sample_neighbor(current.tours)
            if neighbor is None:
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

            if show_progress:
                progress.set_postfix(
                    current_loss=f"{current.loss:,.0f}",
                    best_loss=f"{best.loss:,.0f}",
                    temperature=f"{temperature:.2f}",
                    refresh=False,
                )

        return best

    def optimize_parallel(
        self,
        steps: int,
        n_runs: int,
        *,
        show_progress: bool = True,
    ) -> Solution:
        if steps <= 0:
            raise ValueError("steps must be positive")
        if n_runs <= 0:
            raise ValueError("n_runs must be positive")

        solvers = [
            SimulatedAnnealingSolver(
                self.problem,
                seed=self.rng.getrandbits(64),
            )
            for _ in range(n_runs)
        ]

        with ProcessPoolExecutor() as executor:
            futures = [
                executor.submit(
                    solver.optimize,
                    steps,
                    show_progress=False,
                )
                for solver in solvers
            ]
            solutions = [
                future.result()
                for future in tqdm(
                    as_completed(futures),
                    total=n_runs,
                    desc="Simulated annealing runs",
                    unit="run",
                    disable=not show_progress,
                )
            ]

        return min(solutions, key=lambda solution: solution.loss)


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
    arguments = parser.parse_args()

    problem = ProblemData(*load_data(arguments.filepath))
    solver = SimulatedAnnealingSolver(problem, seed=arguments.seed)

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
