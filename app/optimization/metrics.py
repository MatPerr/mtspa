from math import sqrt
from typing import Sequence

from app.optimization.datamodel import (
    AgentId,
    ProblemData,
    SolutionMetrics,
    Tour,
    TourMetrics,
)


def compute_std(
    total: int | float,
    sum_of_squares: int | float,
    count: int,
) -> float:
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
    distance = 0
    travel_time = 0
    lateness = 0
    waiting_time = 0
    overtime = 0
    current_time = problem.agent_start_times[agent_id]

    for origin, destination in zip(tour, tour[1:]):
        leg_travel_time = problem.travel_times[origin][destination]
        distance += problem.distances[origin][destination]
        travel_time += leg_travel_time
        arrival_time = current_time + leg_travel_time

        if problem.node_is_home[destination]:
            overtime = max(
                0,
                arrival_time - problem.agent_end_times[agent_id],
            )
            current_time = arrival_time
            continue

        scheduled_time = problem.node_times[destination]
        time_difference = arrival_time - scheduled_time
        waiting_time += max(0, -time_difference)
        lateness += max(0, time_difference)
        current_time = (
            max(arrival_time, scheduled_time)
            + problem.node_durations[destination]
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
