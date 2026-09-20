import argparse
import math
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from app.optimization.datamodel import NodeId, ProblemData, Solution, Tours
from app.optimization.loss_calibration import resolve_loss_configs
from app.optimization.metrics import calculate_solution_metrics, calculate_tour_metrics
from app.optimization.objectives import (
    DEFAULT_LOSS_CONFIG,
    LOSS_CONFIGS,
    AnyLossConfig,
    MetricName,
    ResolvedLossConfig,
    calculate_loss,
)
from app.optimization.problem_io import load_data
from app.optimization.reporting import save_solution_report
from app.optimization.results import ConfigOptimizationResult

DEFAULT_MAX_STATES = 8_000_000
type ProgressCallback = Callable[[int, int], None]


class StateLimitExceededError(RuntimeError):
    def __init__(self, appointment_id: NodeId, max_states: int) -> None:
        self.appointment_id = appointment_id
        self.max_states = max_states
        super().__init__(
            "DP stopped before its state limit was exceeded while assigning "
            f"appointment {appointment_id}: maximum {max_states:,} states"
        )


class DynamicProgrammingSolver:
    def __init__(
        self,
        problem: ProblemData,
        max_states: int = DEFAULT_MAX_STATES,
        loss_configs: Sequence[AnyLossConfig] = (DEFAULT_LOSS_CONFIG,),
    ) -> None:
        if max_states <= 0:
            raise ValueError("max_states must be positive")
        if not 1 <= len(loss_configs) <= 2:
            raise ValueError("DP requires one or two loss configs")
        if len({config.id for config in loss_configs}) != len(loss_configs):
            raise ValueError("DP loss configs must not contain duplicates")
        for config in loss_configs:
            if "dp" not in config.supported_solvers:
                raise ValueError(
                    f"Loss config {config.name!r} is not supported by DP"
                )

        self.problem = problem
        self.max_states = max_states
        self.loss_configs = resolve_loss_configs(problem, loss_configs)
        self.final_state_count = 0
        self.elapsed_seconds = 0.0

    def evaluate_tours(
        self,
        tours: Tours,
        loss_config: ResolvedLossConfig | None = None,
    ) -> Solution:
        config = loss_config or self.loss_configs[0]
        metrics_by_tour = [
            calculate_tour_metrics(self.problem, agent_id, tour)
            for agent_id, tour in enumerate(tours)
        ]
        metrics = calculate_solution_metrics(metrics_by_tour)

        return Solution(
            tours=tours,
            tour_metrics=metrics_by_tour,
            metrics=metrics,
            loss=calculate_loss(metrics, config),
        )

    def optimize(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> Solution:
        if len(self.loss_configs) != 1:
            raise ValueError(
                "optimize() requires one config; use "
                "optimize_for_loss_configs() for multiple configs"
            )
        return self.optimize_for_loss_configs(
            progress_callback=progress_callback,
        )[0].solution

    def optimize_for_loss_configs(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> list[ConfigOptimizationResult]:
        distances = self.problem.distances
        travel_times = self.problem.travel_times
        node_times = self.problem.node_times
        node_durations = self.problem.node_durations
        agent_home_nodes = self.problem.agent_home_nodes
        agent_start_times = self.problem.agent_start_times
        can_follow = self.problem.can_follow
        return_home_feasible = self.problem.can_return_home
        config_weights = []
        for config in self.loss_configs:
            weights = {
                term.metric: term.weight
                for term in config.terms
            }
            config_weights.append(
                (
                    weights.get(MetricName.TOTAL_DISTANCE, 0),
                    weights.get(MetricName.TOTAL_WAITING_TIME, 0),
                )
            )
        config_count = len(self.loss_configs)
        first_distance_weight, first_waiting_weight = config_weights[0]
        second_distance_weight, second_waiting_weight = (
            config_weights[1]
            if config_count == 2
            else (0, 0)
        )
        agent_ids = range(len(agent_home_nodes))
        agent_count = len(agent_ids)
        appointment_ids = sorted(
            self.problem.appointment_ids,
            key=lambda node_id: (node_times[node_id], node_id),
        )
        initial_state = tuple(agent_home_nodes)
        states: dict[
            tuple[NodeId, ...],
            tuple[float, int] | tuple[float, int, float, int],
        ] = {
            initial_state: (
                (0, 0)
                if config_count == 1
                else (0, 0, 0, 0)
            )
        }
        reported_state_count = len(states)
        last_reported_percent = len(states) * 100 // self.max_states
        next_report_at = max(
            1,
            ((last_reported_percent + 1) * self.max_states + 99) // 100,
        )
        if progress_callback is not None:
            progress_callback(len(states), self.max_states)
        started = time.perf_counter()

        for appointment_id in appointment_ids:
            next_states: dict[
                tuple[NodeId, ...],
                tuple[float, int] | tuple[float, int, float, int],
            ] = {}

            for state, config_records in states.items():
                for slot in agent_ids:
                    previous_id = state[slot]
                    if not can_follow[previous_id][appointment_id]:
                        continue

                    next_state = (
                        state[:slot]
                        + (appointment_id,)
                        + state[slot + 1 :]
                    )
                    departure_time = (
                        agent_start_times[slot]
                        if previous_id == agent_home_nodes[slot]
                        else node_times[previous_id]
                        + node_durations[previous_id]
                    )
                    waiting_time = (
                        node_times[appointment_id]
                        - departure_time
                        - travel_times[previous_id][appointment_id]
                    )
                    travelled_distance = distances[previous_id][appointment_id]
                    incumbent = next_states.get(next_state)

                    if config_count == 1:
                        loss_so_far, assignment_code = config_records
                        candidate_loss = (
                            loss_so_far
                            + first_distance_weight * travelled_distance
                            + first_waiting_weight * waiting_time
                        )
                        candidate_records = (
                            candidate_loss,
                            assignment_code * agent_count + slot,
                        )
                    else:
                        (
                            first_loss,
                            first_code,
                            second_loss,
                            second_code,
                        ) = config_records
                        candidate_records = (
                            first_loss
                            + first_distance_weight * travelled_distance
                            + first_waiting_weight * waiting_time,
                            first_code * agent_count + slot,
                            second_loss
                            + second_distance_weight * travelled_distance
                            + second_waiting_weight * waiting_time,
                            second_code * agent_count + slot,
                        )

                    if incumbent is None:
                        if len(next_states) >= self.max_states:
                            raise StateLimitExceededError(
                                appointment_id,
                                self.max_states,
                            )
                        next_states[next_state] = candidate_records
                        if progress_callback is not None:
                            state_count = len(next_states)
                            if state_count >= next_report_at:
                                progress_callback(
                                    state_count,
                                    self.max_states,
                                )
                                reported_state_count = state_count
                                last_reported_percent = (
                                    state_count * 100 // self.max_states
                                )
                                next_report_at = (
                                    (last_reported_percent + 1)
                                    * self.max_states
                                    + 99
                                ) // 100
                    elif config_count == 1:
                        if candidate_records[0] < incumbent[0]:
                            next_states[next_state] = candidate_records
                    else:
                        first_improves = candidate_records[0] < incumbent[0]
                        second_improves = candidate_records[2] < incumbent[2]
                        if first_improves or second_improves:
                            next_states[next_state] = (
                                candidate_records[0]
                                if first_improves
                                else incumbent[0],
                                candidate_records[1]
                                if first_improves
                                else incumbent[1],
                                candidate_records[2]
                                if second_improves
                                else incumbent[2],
                                candidate_records[3]
                                if second_improves
                                else incumbent[3],
                            )

            if not next_states:
                raise ValueError(
                    "No feasible assignments remain after appointment "
                    f"{appointment_id}"
                )

            if (
                progress_callback is not None
                and len(next_states) > reported_state_count
            ):
                reported_state_count = len(next_states)
                progress_callback(reported_state_count, self.max_states)
                last_reported_percent = (
                    reported_state_count * 100 // self.max_states
                )
                next_report_at = (
                    (last_reported_percent + 1)
                    * self.max_states
                    + 99
                ) // 100

            states = next_states

        best_records: list[tuple[float, int] | None] = [
            None for _ in self.loss_configs
        ]

        for state, config_records in states.items():
            return_distance = 0
            can_return = True

            for agent_id in agent_ids:
                last_id = state[agent_id]
                home_id = agent_home_nodes[agent_id]
                if last_id == home_id:
                    continue

                if not return_home_feasible[agent_id][last_id]:
                    can_return = False
                    break

                return_distance += distances[last_id][home_id]

            if not can_return:
                continue

            config_records_for_state = (
                ((config_records[0], config_records[1]),)
                if config_count == 1
                else (
                    (config_records[0], config_records[1]),
                    (config_records[2], config_records[3]),
                )
            )
            for config_id, (
                (loss_so_far, assignment_code),
                (distance_weight, _),
            ) in enumerate(
                zip(
                    config_records_for_state,
                    config_weights,
                    strict=True,
                )
            ):
                candidate_loss = (
                    loss_so_far
                    + distance_weight * return_distance
                )
                incumbent = best_records[config_id]
                if incumbent is None or candidate_loss < incumbent[0]:
                    best_records[config_id] = (
                        candidate_loss,
                        assignment_code,
                    )

        if any(record is None for record in best_records):
            raise ValueError(
                "No solution lets every agent return home before endTime"
            )

        self.final_state_count = len(states)
        self.elapsed_seconds = time.perf_counter() - started
        results = []

        for config, best_record in zip(
            self.loss_configs,
            best_records,
            strict=True,
        ):
            if best_record is None:
                raise AssertionError("DP config result is missing")
            best_loss, best_code = best_record
            assignments = [0] * len(appointment_ids)
            remaining_code = best_code
            for index in range(len(appointment_ids) - 1, -1, -1):
                assignments[index] = remaining_code % agent_count
                remaining_code //= agent_count

            tours = [[home_node] for home_node in agent_home_nodes]
            for appointment_id, slot in zip(
                appointment_ids,
                assignments,
                strict=True,
            ):
                tours[agent_ids[slot]].append(appointment_id)
            for agent_id in agent_ids:
                tours[agent_id].append(agent_home_nodes[agent_id])

            solution = self.evaluate_tours(tours, config)

            if not math.isclose(solution.loss, best_loss):
                raise AssertionError(
                    "Reconstructed tours do not match the DP loss"
                )
            if solution.metrics.total_lateness != 0:
                raise AssertionError("DP solution contains late appointments")
            if solution.metrics.total_overtime != 0:
                raise AssertionError("DP solution returns an agent home late")

            results.append(ConfigOptimizationResult(config, solution))

        return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Solve the fixed-time routing problem exactly for distance"
    )
    parser.add_argument(
        "filepath",
        nargs="?",
        type=Path,
        default=Path("data/data.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts"),
    )
    parser.add_argument(
        "--max-states",
        type=int,
        default=DEFAULT_MAX_STATES,
    )
    parser.add_argument(
        "--loss-config",
        choices=[
            config_id
            for config_id, config in LOSS_CONFIGS.items()
            if "dp" in config.supported_solvers
        ],
        default=DEFAULT_LOSS_CONFIG.id,
    )
    arguments = parser.parse_args()

    problem = ProblemData(*load_data(arguments.filepath))
    optimizer = DynamicProgrammingSolver(
        problem,
        max_states=arguments.max_states,
        loss_configs=(LOSS_CONFIGS[arguments.loss_config],),
    )
    solution = optimizer.optimize()
    summary_path, svg_path = save_solution_report(
        problem,
        solution,
        optimizer.final_state_count,
        optimizer.elapsed_seconds,
        arguments.output,
    )

    print(f"Total distance: {solution.metrics.total_distance / 1000:.3f} km")
    print(f"Total gain per hour: {solution.metrics.total_gain_per_hour:.3f}")
    print(f"Gain-per-hour standard deviation: {solution.metrics.gain_per_hour_std:.3f}")
    print(f"Total lateness: {solution.metrics.total_lateness / 60:.1f} min")
    print(f"Total waiting time: {solution.metrics.total_waiting_time / 60:.1f} min")
    print(f"Waiting-time standard deviation: {solution.metrics.waiting_time_std / 60:.1f} min")
    print(f"Total overtime: {solution.metrics.total_overtime / 60:.1f} min")
    print(f"Overtime standard deviation: {solution.metrics.overtime_std / 60:.1f} min")
    print(f"Final DP states: {optimizer.final_state_count:,}")
    print(f"Elapsed: {optimizer.elapsed_seconds:.3f} s")
    print(f"Summary: {summary_path}")
    print(f"Visualization: {svg_path}")


if __name__ == "__main__":
    main()
