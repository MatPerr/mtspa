"""Build display timelines for finished solutions using the solver's time model."""

from itertools import pairwise

from app.optimization.datamodel import AgentId, NodeId, ProblemData, Tour
from app.schemas import TimelineSegmentResponse, TourTimelineResponse


def build_tour_timeline(
    problem: ProblemData,
    agent_id: AgentId,
    tour: Tour,
    appointment_id_by_node: dict[NodeId, int],
) -> TourTimelineResponse:
    workday_start = problem.agent_start_times[agent_id]
    workday_end = problem.agent_end_times[agent_id]
    current_time = workday_start
    segments: list[TimelineSegmentResponse] = []

    def add_segment(
        kind: str,
        start: int,
        end: int,
        appointment_id: int | None = None,
    ) -> None:
        # Keep zero-duration appointment markers, but omit empty time intervals.
        if end > start or kind == "appointment":
            segments.append(TimelineSegmentResponse(
                kind=kind,
                start_time=start,
                end_time=end,
                appointment_id=appointment_id,
            ))

    for origin_id, destination_id in pairwise(tour):
        appointment_id = appointment_id_by_node.get(destination_id)
        arrival_time = current_time + problem.travel_times[origin_id][destination_id]
        add_segment("travel", current_time, arrival_time, appointment_id)
        if problem.node_is_home[destination_id]:
            current_time = arrival_time
            continue

        scheduled_time = problem.node_times[destination_id]
        service_start = max(arrival_time, scheduled_time)
        add_segment("waiting", arrival_time, service_start, appointment_id)
        # Lateness overlaps actual activity; it must not extend the activity bar.
        add_segment("lateness", scheduled_time, arrival_time, appointment_id)
        current_time = service_start + problem.node_durations[destination_id]
        add_segment("appointment", service_start, current_time, appointment_id)

    return_time = current_time
    end_time = max(workday_end, return_time)
    add_segment("available", return_time, workday_end)
    add_segment("overtime", workday_end, return_time)

    return TourTimelineResponse(
        end_time=end_time,
        workday_start=workday_start,
        workday_end=workday_end,
        return_time=return_time,
        segments=segments,
    )
