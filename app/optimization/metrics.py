from itertools import pairwise
from math import sqrt
from typing import Sequence

from app.optimization.datamodel import (
    AgentId,
    ProblemData,
    SolutionMetrics,
    Tour,
    TourMetrics,
    Tours,
)


def compute_std(
    total: int | float,
    sum_of_squares: int | float,
    count: int,
) -> float:
    """Compute a population standard deviation from aggregate values.

    Args:
        total: Sum of the observations.
        sum_of_squares: Sum of the squared observations.
        count: Positive number of observations.

    Returns:
        Population standard deviation, clamping negative rounding error in
        the variance to zero.

    Raises:
        ValueError: count is not positive.
    """
    if count <= 0:
        raise ValueError("compute_std requires a positive count")

    mean = total / count
    variance = sum_of_squares / count - mean * mean
    return sqrt(max(0.0, variance))


def calculate_tour_metrics(
    problem: ProblemData,
    agent_id: AgentId,
    tour: Tour,
) -> TourMetrics:
    """Simulate a route to calculate distance, timing, and earnings metrics.

    Service starts at the later of arrival and the scheduled appointment time,
    so lateness can propagate to subsequent stops. Waiting measures early
    arrivals, and overtime measures returning home after the workday ends.

    Args:
        problem: Routing data with distances in metres and times in seconds.
        agent_id: Agent whose workday is used for the simulation.
        tour: Node IDs in visit order, starting and ending at the agent's home.
            The sequence is evaluated as supplied, without sorting or mutation.

    Returns:
        Route metrics, including gain per kilometre and per elapsed hour.
        Elapsed time runs from workday start to the return home.
    """
    distance = 0
    travel_time = 0
    lateness = 0
    waiting_time = 0
    overtime = 0
    current_time = problem.agent_start_times[agent_id]

    for origin_id, destination_id in pairwise(tour):
        leg_travel_time = problem.travel_times[origin_id][destination_id]
        distance += problem.distances[origin_id][destination_id]
        travel_time += leg_travel_time
        arrival_time = current_time + leg_travel_time

        if problem.node_is_home[destination_id]:
            overtime = max(
                0,
                arrival_time - problem.agent_end_times[agent_id],
            )
            current_time = arrival_time
            continue

        scheduled_time = problem.node_times[destination_id]
        time_difference = arrival_time - scheduled_time
        waiting_time += max(0, -time_difference)
        lateness += max(0, time_difference)
        current_time = (
            max(arrival_time, scheduled_time)
            + problem.node_durations[destination_id]
        )

    gain = sum(problem.node_gains[node_id] for node_id in tour[1:-1])
    elapsed_time = current_time - problem.agent_start_times[agent_id]

    return TourMetrics(
        distance=distance,
        travel_time=travel_time,
        gain=gain,
        elapsed_time=elapsed_time,
        gain_per_km=(
            gain / (distance / 1000)
            if distance > 0
            else 0.0
        ),
        gain_per_hour=(
            gain / (elapsed_time / 3600)
            if elapsed_time > 0
            else 0.0
        ),
        lateness=lateness,
        waiting_time=waiting_time,
        overtime=overtime,
    )


def calculate_solution_metrics(
    tour_metrics: Sequence[TourMetrics],
) -> SolutionMetrics:
    """Combine route metrics into totals and population standard deviations.

    Overall gain rates divide total gain by total distance or elapsed time;
    they are not averages of the individual agents' rates. Agents with empty
    routes still contribute to the population standard deviations.

    Args:
        tour_metrics: Nonempty sequence containing one record per agent.

    Returns:
        Aggregated metrics with distances in metres, times in seconds, and
        gain rates per kilometre or hour. Rates with zero denominators are zero.

    Raises:
        ValueError: tour_metrics is empty.
    """
    if not tour_metrics:
        raise ValueError("At least one tour is required")

    count = len(tour_metrics)
    total_distance = 0
    distance_sum_of_squares = 0
    total_travel_time = 0
    travel_time_sum_of_squares = 0
    total_gain = 0
    gain_sum_of_squares = 0
    total_elapsed_time = 0
    gain_per_km_sum = 0.0
    gain_per_km_sum_of_squares = 0.0
    gain_per_hour_sum = 0.0
    gain_per_hour_sum_of_squares = 0.0
    total_lateness = 0
    total_waiting_time = 0
    waiting_time_sum_of_squares = 0
    total_overtime = 0
    overtime_sum_of_squares = 0

    for metrics in tour_metrics:
        total_distance += metrics.distance
        distance_sum_of_squares += metrics.distance * metrics.distance
        total_travel_time += metrics.travel_time
        travel_time_sum_of_squares += (
            metrics.travel_time * metrics.travel_time
        )
        total_gain += metrics.gain
        gain_sum_of_squares += metrics.gain * metrics.gain
        total_elapsed_time += metrics.elapsed_time
        gain_per_km_sum += metrics.gain_per_km
        gain_per_km_sum_of_squares += (
            metrics.gain_per_km * metrics.gain_per_km
        )
        gain_per_hour_sum += metrics.gain_per_hour
        gain_per_hour_sum_of_squares += (
            metrics.gain_per_hour * metrics.gain_per_hour
        )
        total_lateness += metrics.lateness
        total_waiting_time += metrics.waiting_time
        waiting_time_sum_of_squares += (
            metrics.waiting_time * metrics.waiting_time
        )
        total_overtime += metrics.overtime
        overtime_sum_of_squares += metrics.overtime * metrics.overtime

    return SolutionMetrics(
        total_distance=total_distance,
        distance_std=compute_std(
            total_distance,
            distance_sum_of_squares,
            count,
        ),
        total_travel_time=total_travel_time,
        travel_time_std=compute_std(
            total_travel_time,
            travel_time_sum_of_squares,
            count,
        ),
        total_gain=total_gain,
        gain_std=compute_std(total_gain, gain_sum_of_squares, count),
        total_gain_per_km=(
            total_gain / (total_distance / 1000)
            if total_distance > 0
            else 0.0
        ),
        gain_per_km_std=compute_std(
            gain_per_km_sum,
            gain_per_km_sum_of_squares,
            count,
        ),
        total_gain_per_hour=(
            total_gain / (total_elapsed_time / 3600)
            if total_elapsed_time > 0
            else 0.0
        ),
        gain_per_hour_std=compute_std(
            gain_per_hour_sum,
            gain_per_hour_sum_of_squares,
            count,
        ),
        total_lateness=total_lateness,
        total_waiting_time=total_waiting_time,
        waiting_time_std=compute_std(
            total_waiting_time,
            waiting_time_sum_of_squares,
            count,
        ),
        total_overtime=total_overtime,
        overtime_std=compute_std(
            total_overtime,
            overtime_sum_of_squares,
            count,
        ),
    )


def calculate_metrics(
    problem: ProblemData,
    tours: Tours,
    *,
    previous_metrics: list[TourMetrics] | None = None,
    changed_agent_ids: tuple[AgentId, ...] | None = None,
) -> tuple[list[TourMetrics], SolutionMetrics]:
    """Calculate all route metrics or reuse cached metrics for unchanged routes.

    Args:
        problem: Routing data used to simulate routes.
        tours: Routes indexed by agent ID, including their home endpoints.
        previous_metrics: Cached route metrics indexed by agent ID, or None to
            evaluate every route. Unchanged records must still match their tours.
        changed_agent_ids: IDs of every changed route, required exactly when
            previous_metrics is supplied. An empty tuple reuses every record.

    Returns:
        A new list of per-route metrics and their combined solution metrics.
        The input tours and previous_metrics list are left unchanged.

    Raises:
        ValueError: Only one of previous_metrics and changed_agent_ids is
            supplied, or no tour metrics are available to aggregate.
    """
    if previous_metrics is None:
        if changed_agent_ids is not None:
            raise ValueError("changed_agent_ids requires previous_metrics")
        metrics_by_tour = [
            calculate_tour_metrics(problem, agent_id, tour)
            for agent_id, tour in enumerate(tours)
        ]
    else:
        if changed_agent_ids is None:
            raise ValueError("changed_agent_ids is required with previous_metrics")
        metrics_by_tour = previous_metrics.copy()

        for agent_id in changed_agent_ids:
            metrics_by_tour[agent_id] = calculate_tour_metrics(
                problem,
                agent_id,
                tours[agent_id],
            )

    combined_metrics = calculate_solution_metrics(metrics_by_tour)

    return metrics_by_tour, combined_metrics
