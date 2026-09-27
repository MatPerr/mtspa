"""Single-objective dynamic programming without application concerns."""

import math

from app.optimization.datamodel import NodeId, ProblemData, Solution, Tours
from app.optimization.loss_calibration import calibrate_loss_weights
from app.optimization.metrics import calculate_solution_metrics, calculate_tour_metrics
from app.optimization.objectives import (
    DEFAULT_LOSS_CONFIG,
    LossConfig,
    MetricName,
    calculate_loss,
)
from app.optimization.solvers.dp_reconstruction import reconstruct_tours

DEFAULT_MAX_STATES = 8_000_000


class StateLimitExceededError(RuntimeError):
    pass


class DynamicProgrammingSolver:
    def __init__(
        self,
        problem: ProblemData,
        max_states: int = DEFAULT_MAX_STATES,
        loss_config: LossConfig = DEFAULT_LOSS_CONFIG,
        *,
        weights: dict[MetricName, float] | None = None,
    ) -> None:
        """Validate the state limit and calibrate one DP-compatible objective.

        Args:
            problem: Routing problem with fixed appointment times.
            max_states: Positive maximum number of states in one DP layer.
            loss_config: Objective metadata and importances supported by DP.
            weights: Optional weights already calibrated for this problem and
                objective. Copy them when supplied; otherwise calibrate once.

        Raises:
            ValueError: max_states is not positive or the objective rejects DP.
        """
        if max_states <= 0:
            raise ValueError("max_states must be positive")
        if "dp" not in loss_config.supported_solvers:
            raise ValueError(
                f"Loss config {loss_config.name!r} is not supported by DP"
            )

        self.problem = problem
        self.max_states = max_states
        self.loss_config = loss_config
        self.weights = (
            calibrate_loss_weights(problem, loss_config.importances)
            if weights is None
            else weights.copy()
        )
        self.final_state_count = 0

    def evaluate_tours(self, tours: Tours) -> Solution:
        """Calculate complete route metrics and the configured objective's loss.

        Args:
            tours: Routes indexed by agent ID, including home endpoints.

        Returns:
            A solution referencing tours and containing newly computed metrics
            and loss. Evaluation itself does not enforce DP feasibility.
        """
        metrics_by_tour = [
            calculate_tour_metrics(self.problem, agent_id, tour)
            for agent_id, tour in enumerate(tours)
        ]
        metrics = calculate_solution_metrics(metrics_by_tour)
        return Solution(
            tours=tours,
            tour_metrics=metrics_by_tour,
            metrics=metrics,
            loss=calculate_loss(metrics, self.weights),
        )

    def optimize(self) -> Solution:
        """Find the minimum-loss assignment satisfying all timing constraints.

        Process appointments by (scheduled time, node ID). A state stores each
        agent's last node; its value holds the cheapest partial loss and an
        assignment history encoded as a base-agent-count integer. Merge paths
        reaching the same state, add feasible trips home, and decode the best
        history into routes. Record the last layer's size in final_state_count
        before return-home filtering.

        Returns:
            Exact optimum for the configured supported objective, with every
            appointment assigned once and no lateness or overtime.

        Raises:
            StateLimitExceededError: A DP layer would exceed max_states.
            ValueError: No feasible assignment or on-time return home exists.
            AssertionError: Reconstructed routes disagree with the DP loss or
                violate the timing constraints.
        """
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
        distance_weight = self.weights.get(MetricName.TOTAL_DISTANCE, 0)
        waiting_time_weight = self.weights.get(MetricName.TOTAL_WAITING_TIME, 0)

        initial_state = tuple(agent_home_nodes)
        # Key: last visited node for each agent; (4, 7) means agents 0 and 1
        # last visited nodes 4 and 7. Value: (best partial loss, assignment code).
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
                    best_known_record = next_states.get(next_state)

                    if best_known_record is None:
                        if len(next_states) >= self.max_states:
                            raise StateLimitExceededError(
                                f"DP exceeded {self.max_states:,} states"
                            )
                        next_states[next_state] = (next_loss, next_code)
                    elif next_loss < best_known_record[0]:
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
        tours = reconstruct_tours(problem, appointment_ids, assignment_code)
        self.final_state_count = len(states)
        solution = self.evaluate_tours(tours)
        if not math.isclose(solution.loss, best_loss):
            raise AssertionError("Reconstructed tours do not match the DP loss")
        if solution.metrics.total_lateness != 0:
            raise AssertionError("DP solution contains late appointments")
        if solution.metrics.total_overtime != 0:
            raise AssertionError("DP solution returns an agent home late")
        return solution
