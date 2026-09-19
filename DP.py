import argparse
import time
from pathlib import Path

from datamodel import NodeId, ProblemData, Solution, Tours
from metrics import tour_metrics
from reporting import save_solution_report
from utils import load_data


class DynamicProgrammingSolver:
    def __init__(self, problem: ProblemData) -> None:
        self.problem = problem
        self.final_state_count = 0
        self.elapsed_seconds = 0.0

    def evaluate_tours(self, tours: Tours) -> Solution:
        metrics = tour_metrics(self.problem, tours)

        return Solution(
            tours=tours,
            metrics=metrics,
            loss=metrics.total_distance,
        )

    def optimize(self) -> Solution:
        distances = self.problem.distances
        node_times = self.problem.node_times
        agent_home_nodes = self.problem.agent_home_nodes
        can_follow = self.problem.can_follow
        return_home_feasible = self.problem.can_return_home
        agent_ids = range(len(agent_home_nodes))
        agent_count = len(agent_ids)
        appointment_ids = sorted(
            self.problem.appointment_ids,
            key=lambda node_id: (node_times[node_id], node_id),
        )
        initial_state = tuple(agent_home_nodes)
        states: dict[tuple[NodeId, ...], tuple[int, int]] = {
            initial_state: (0, 0)
        }
        started = time.perf_counter()

        for appointment_id in appointment_ids:
            next_states: dict[tuple[NodeId, ...], tuple[int, int]] = {}

            for state, (distance_so_far, assignment_code) in states.items():
                for slot in agent_ids:
                    previous_id = state[slot]
                    if not can_follow[previous_id][appointment_id]:
                        continue

                    next_state = (
                        state[:slot]
                        + (appointment_id,)
                        + state[slot + 1 :]
                    )
                    next_distance = (
                        distance_so_far
                        + distances[previous_id][appointment_id]
                    )
                    next_code = assignment_code * agent_count + slot
                    incumbent = next_states.get(next_state)

                    if incumbent is None or next_distance < incumbent[0]:
                        next_states[next_state] = (next_distance, next_code)

            if not next_states:
                raise ValueError(
                    "No feasible assignments remain after appointment "
                    f"{appointment_id}"
                )

            states = next_states

        best_distance: int | None = None
        best_code: int | None = None

        for state, (distance_so_far, assignment_code) in states.items():
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

            candidate_distance = distance_so_far + return_distance
            if can_return and (
                best_distance is None
                or candidate_distance < best_distance
            ):
                best_distance = candidate_distance
                best_code = assignment_code

        if best_distance is None or best_code is None:
            raise ValueError(
                "No solution lets every agent return home before endTime"
            )

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

        self.final_state_count = len(states)
        self.elapsed_seconds = time.perf_counter() - started
        solution = self.evaluate_tours(tours)

        if solution.metrics.total_distance != best_distance:
            raise AssertionError("Reconstructed tours do not match the DP cost")
        if solution.metrics.total_lateness != 0:
            raise AssertionError("DP solution contains late appointments")
        if solution.metrics.total_overtime != 0:
            raise AssertionError("DP solution returns an agent home late")

        return solution


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
    arguments = parser.parse_args()

    problem = ProblemData(*load_data(arguments.filepath))
    optimizer = DynamicProgrammingSolver(problem)
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
