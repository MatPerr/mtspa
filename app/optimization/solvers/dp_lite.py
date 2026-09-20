"""Single-objective dynamic programming without application concerns."""

import math

from app.optimization.datamodel import NodeId, ProblemData, Solution, Tours
from app.optimization.loss_calibration import resolve_loss_config
from app.optimization.metrics import calculate_solution_metrics, calculate_tour_metrics
from app.optimization.objectives import (
    DEFAULT_LOSS_CONFIG,
    AnyLossConfig,
    MetricName,
    calculate_loss,
)

DEFAULT_MAX_STATES = 8_000_000


class StateLimitExceededError(RuntimeError):
    pass


class DynamicProgrammingSolver:
    def __init__(
        self,
        problem: ProblemData,
        max_states: int = DEFAULT_MAX_STATES,
        loss_config: AnyLossConfig = DEFAULT_LOSS_CONFIG,
    ) -> None:
        if max_states <= 0:
            raise ValueError("max_states must be positive")
        if "dp" not in loss_config.supported_solvers:
            raise ValueError(
                f"Loss config {loss_config.name!r} is not supported by DP"
            )

        self.problem = problem
        self.max_states = max_states
        self.loss_config = resolve_loss_config(problem, loss_config)
        self.final_state_count = 0

    def evaluate_tours(self, tours: Tours) -> Solution:
        metrics_by_tour = [
            calculate_tour_metrics(self.problem, agent_id, tour)
            for agent_id, tour in enumerate(tours)
        ]
        metrics = calculate_solution_metrics(metrics_by_tour)
        return Solution(
            tours=tours,
            tour_metrics=metrics_by_tour,
            metrics=metrics,
            loss=calculate_loss(metrics, self.loss_config),
        )

    def optimize(self) -> Solution:
        problem = self.problem
        distances = problem.distances
        travel_times = problem.travel_times
        node_times = problem.node_times
        node_durations = problem.node_durations
        agent_home_nodes = problem.agent_home_nodes
        agent_start_times = problem.agent_start_times
        can_follow = problem.can_follow
        can_return_home = problem.can_return_home
        agent_ids = range(len(agent_home_nodes))
        agent_count = len(agent_home_nodes)
        appointment_ids = sorted(
            problem.appointment_ids,
            key=lambda node_id: (node_times[node_id], node_id),
        )
        weights = {
            term.metric: term.weight
            for term in self.loss_config.terms
        }
        distance_weight = weights.get(MetricName.TOTAL_DISTANCE, 0)
        waiting_time_weight = weights.get(MetricName.TOTAL_WAITING_TIME, 0)

        initial_state = tuple(agent_home_nodes)
        states: dict[tuple[NodeId, ...], tuple[float, int]] = {
            initial_state: (0, 0)
        }

        for appointment_id in appointment_ids:
            next_states: dict[tuple[NodeId, ...], tuple[float, int]] = {}

            for state, (loss_so_far, assignment_code) in states.items():
                for agent_id in agent_ids:
                    previous_id = state[agent_id]
                    if not can_follow[previous_id][appointment_id]:
                        continue

                    next_state = (
                        state[:agent_id]
                        + (appointment_id,)
                        + state[agent_id + 1 :]
                    )
                    departure_time = (
                        agent_start_times[agent_id]
                        if previous_id == agent_home_nodes[agent_id]
                        else node_times[previous_id]
                        + node_durations[previous_id]
                    )
                    waiting_time = (
                        node_times[appointment_id]
                        - departure_time
                        - travel_times[previous_id][appointment_id]
                    )
                    next_loss = (
                        loss_so_far
                        + distance_weight
                        * distances[previous_id][appointment_id]
                        + waiting_time_weight * waiting_time
                    )
                    next_code = assignment_code * agent_count + agent_id
                    incumbent = next_states.get(next_state)

                    if incumbent is None:
                        if len(next_states) >= self.max_states:
                            raise StateLimitExceededError(
                                f"DP exceeded {self.max_states:,} states"
                            )
                        next_states[next_state] = (next_loss, next_code)
                    elif next_loss < incumbent[0]:
                        next_states[next_state] = (next_loss, next_code)

            if not next_states:
                raise ValueError(
                    "No feasible assignments remain after appointment "
                    f"{appointment_id}"
                )
            states = next_states

        best_record: tuple[float, int] | None = None

        for state, (loss_so_far, assignment_code) in states.items():
            return_distance = 0
            for agent_id in agent_ids:
                last_id = state[agent_id]
                home_id = agent_home_nodes[agent_id]
                if not can_return_home[agent_id][last_id]:
                    break
                return_distance += distances[last_id][home_id]
            else:
                candidate_loss = (
                    loss_so_far
                    + distance_weight * return_distance
                )
                if best_record is None or candidate_loss < best_record[0]:
                    best_record = candidate_loss, assignment_code

        if best_record is None:
            raise ValueError(
                "No solution lets every agent return home before endTime"
            )

        best_loss, assignment_code = best_record
        assignments = [0] * len(appointment_ids)
        for index in range(len(appointment_ids) - 1, -1, -1):
            assignments[index] = assignment_code % agent_count
            assignment_code //= agent_count

        tours = [[home_node] for home_node in agent_home_nodes]
        for appointment_id, agent_id in zip(
            appointment_ids,
            assignments,
            strict=True,
        ):
            tours[agent_id].append(appointment_id)
        for agent_id in agent_ids:
            tours[agent_id].append(agent_home_nodes[agent_id])

        self.final_state_count = len(states)
        solution = self.evaluate_tours(tours)
        if not math.isclose(solution.loss, best_loss):
            raise AssertionError("Reconstructed tours do not match the DP loss")
        if solution.metrics.total_lateness != 0:
            raise AssertionError("DP solution contains late appointments")
        if solution.metrics.total_overtime != 0:
            raise AssertionError("DP solution returns an agent home late")
        return solution
