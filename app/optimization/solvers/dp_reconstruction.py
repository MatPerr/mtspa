"""Rebuild complete routes from the assignment history stored by DP."""

from app.optimization.datamodel import NodeId, ProblemData, Tours


def reconstruct_tours(
    problem: ProblemData,
    appointment_ids: list[NodeId],
    assignment_code: int,
) -> Tours:
    """Decode an assignment history into one home-to-home route per agent.

    DP appends an agent ID with code = code * agent_count + agent_id.
    Remainder and integer division recover those IDs in reverse order.

    Args:
        problem: Routing data supplying agent count and each agent's home node.
        appointment_ids: Appointment node IDs in the order processed by DP.
        assignment_code: Nonnegative integer encoding one agent ID per
            appointment, using the number of agents as its base.

    Returns:
        New routes indexed by agent ID, with appointments in the supplied order
        and the agent's home at both ends. Agents with no visits get [home, home].
        The problem and appointment_ids are not modified.
    """
    agent_count = len(problem.agents)
    assignments = [0] * len(appointment_ids)

    # Decode every appointment: leading assignments to agent 0 leave no digit.
    for index in range(len(appointment_ids) - 1, -1, -1):
        assignments[index] = assignment_code % agent_count
        assignment_code //= agent_count

    tours = [[home_id] for home_id in problem.agent_home_nodes]
    for appointment_id, agent_id in zip(appointment_ids, assignments, strict=True):
        tours[agent_id].append(appointment_id)
    for agent_id, home_id in enumerate(problem.agent_home_nodes):
        tours[agent_id].append(home_id)

    return tours
