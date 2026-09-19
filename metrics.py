import statistics

from datamodel import ProblemData, TourMetrics, Tours


def tour_metrics(
    problem: ProblemData,
    tours: Tours,
) -> TourMetrics:
    route_distances = []
    route_times = []
    route_gains = []
    route_elapsed_times = []
    route_waiting_times = []
    route_overtimes = []
    total_lateness = 0
    total_waiting_time = 0
    total_overtime = 0

    for agent_id, tour in enumerate(tours):
        distance = 0.0
        travel_time = 0.0
        waiting_time = 0
        overtime = 0
        current_time = problem.agent_start_times[agent_id]

        for origin, destination in zip(tour, tour[1:]):
            distance += problem.distances[origin][destination]
            travel_time += problem.travel_times[origin][destination]
            arrival_time = (
                current_time
                + problem.travel_times[origin][destination]
            )

            if problem.node_is_home[destination]:
                overtime = max(
                    0,
                    arrival_time - problem.agent_end_times[agent_id],
                )
                total_overtime += overtime
                current_time = arrival_time
                continue

            scheduled_time = problem.node_times[destination]
            waiting = max(0, scheduled_time - arrival_time)
            waiting_time += waiting
            total_waiting_time += waiting
            total_lateness += max(0, arrival_time - scheduled_time)
            current_time = (
                max(arrival_time, scheduled_time)
                + problem.node_durations[destination]
            )

        gain = sum(problem.node_gains[node_id] for node_id in tour[1:-1])
        route_distances.append(distance)
        route_times.append(travel_time)
        route_gains.append(gain)
        route_elapsed_times.append(
            current_time - problem.agent_start_times[agent_id]
        )
        route_waiting_times.append(waiting_time)
        route_overtimes.append(overtime)

    total_distance = float(sum(route_distances))
    total_gain = sum(route_gains)
    total_elapsed_time = sum(route_elapsed_times)
    route_gains_per_km = [
        gain / (distance / 1000) if distance > 0 else 0.0
        for gain, distance in zip(
            route_gains,
            route_distances,
            strict=True,
        )
    ]
    route_gains_per_hour = [
        gain / (elapsed_time / 3600) if elapsed_time > 0 else 0.0
        for gain, elapsed_time in zip(
            route_gains,
            route_elapsed_times,
            strict=True,
        )
    ]

    return TourMetrics(
        total_distance=total_distance,
        distance_std=statistics.pstdev(route_distances),
        total_time=float(sum(route_times)),
        time_std=statistics.pstdev(route_times),
        gain_std=statistics.pstdev(route_gains),
        total_gain_per_km=(
            total_gain / (total_distance / 1000)
            if total_distance > 0
            else 0.0
        ),
        gain_per_km_std=statistics.pstdev(route_gains_per_km),
        total_gain_per_hour=(
            total_gain / (total_elapsed_time / 3600)
            if total_elapsed_time > 0
            else 0.0
        ),
        gain_per_hour_std=statistics.pstdev(route_gains_per_hour),
        total_lateness=total_lateness,
        total_waiting_time=total_waiting_time,
        waiting_time_std=statistics.pstdev(route_waiting_times),
        total_overtime=total_overtime,
        overtime_std=statistics.pstdev(route_overtimes),
    )
