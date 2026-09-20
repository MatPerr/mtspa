from collections.abc import Sequence

from app.optimization.datamodel import Agent, Matrix, Node, ProblemData
from app.schemas import AgentInput, AppointmentInput


def input_coordinates(
    agents: Sequence[AgentInput],
    appointments: Sequence[AppointmentInput],
) -> list[tuple[float, float]]:
    return [
        (agent.latitude, agent.longitude)
        for agent in agents
    ] + [
        (appointment.latitude, appointment.longitude)
        for appointment in appointments
    ]


def build_problem(
    agent_inputs: Sequence[AgentInput],
    appointment_inputs: Sequence[AppointmentInput],
    distances: Matrix[int],
    travel_times: Matrix[int],
) -> ProblemData:
    agents = [
        Agent(
            id=agent_id,
            name=agent.name,
            start_time=agent.start_time,
            end_time=agent.end_time,
        )
        for agent_id, agent in enumerate(agent_inputs)
    ]
    nodes = [
        Node(
            id=agent_id,
            latitude=agent.latitude,
            longitude=agent.longitude,
            time=0,
            duration=0,
            kind="home",
            agent_id=agent_id,
            gain=0,
        )
        for agent_id, agent in enumerate(agent_inputs)
    ]
    nodes.extend(
        Node(
            id=len(agents) + appointment_index,
            latitude=appointment.latitude,
            longitude=appointment.longitude,
            time=appointment.time,
            duration=appointment.duration,
            kind="appointment",
            agent_id=None,
            gain=appointment.gain,
        )
        for appointment_index, appointment in enumerate(appointment_inputs)
    )
    return ProblemData(nodes, agents, distances, travel_times)
