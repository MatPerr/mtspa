import random
from bisect import insort_right

from app.optimization.datamodel import AgentId, ProblemData, Tour, Tours

SWAP_PROBABILITY = 0.5


def initialize_random_tours(
    problem: ProblemData,
    rng: random.Random,
) -> Tours:
    """Assign every appointment randomly and order each route by scheduled time.

    Args:
        problem: Routing problem with at least one agent.
        rng: Random generator used to choose an agent for each appointment.

    Returns:
        New routes indexed by agent ID, each bounded by that agent's home.
        Every appointment occurs once; timing feasibility is not enforced.
    """
    appointments_by_agent = [[] for _ in problem.agents]
    for appointment_id in problem.appointment_ids:
        agent_id = rng.randrange(len(problem.agents))
        appointments_by_agent[agent_id].append(appointment_id)

    tours = []
    for agent_id, appointments in enumerate(appointments_by_agent):
        appointments.sort(key=problem.node_times.__getitem__)
        home = problem.agent_home_nodes[agent_id]
        tours.append([home, *appointments, home])

    return tours


def give_appointment(
    problem: ProblemData,
    rng: random.Random,
    donor_tour: Tour,
    receiver_tour: Tour,
) -> None:
    """Move one random appointment between two routes in place.

    The inserted appointment is ordered by scheduled time, then node ID.
    Both home endpoints are preserved. The move does not check feasibility.

    Args:
        problem: Routing data providing appointment times.
        rng: Random generator used to choose the appointment.
        donor_tour: Route containing at least one appointment to remove.
        receiver_tour: Distinct route whose interior is already ordered by
            scheduled time and node ID; it may contain no appointments.

    Raises:
        ValueError: donor_tour contains no appointment to select.
    """
    appointment_index = rng.randrange(1, len(donor_tour) - 1)
    appointment = donor_tour.pop(appointment_index)
    node_times = problem.node_times
    insort_right(
        receiver_tour,
        appointment,
        lo=1,
        hi=len(receiver_tour) - 1,
        key=lambda node_id: (
            node_times[node_id],
            node_id,
        ),
    )


def swap_appointments(
    problem: ProblemData,
    rng: random.Random,
    first_tour: Tour,
    second_tour: Tour,
) -> None:
    """Exchange one appointment from each route in place.

    Select the first appointment randomly, then prefer a partner at the same
    scheduled time. Reinsert both appointments by time and node ID without
    moving the home endpoints or checking timing feasibility.

    Args:
        problem: Routing data providing appointment times.
        rng: Random generator used to choose both appointments.
        first_tour: First route, with a nonempty interior sorted by time and ID.
        second_tour: Distinct route with a nonempty interior sorted by time and ID.

    Raises:
        ValueError: Either route contains no appointment to select.
    """
    first_index = rng.randrange(1, len(first_tour) - 1)
    first_appointment = first_tour[first_index]
    node_times = problem.node_times

    # Prefer exchanging simultaneous appointments
    same_time_indices = [
        index
        for index in range(1, len(second_tour) - 1)
        if node_times[second_tour[index]] == node_times[first_appointment]
    ]
    second_index = (
        rng.choice(same_time_indices)
        if same_time_indices
        else rng.randrange(1, len(second_tour) - 1)
    )

    first_tour.pop(first_index)
    second_appointment = second_tour.pop(second_index)
    for tour, appointment in (
        (first_tour, second_appointment),
        (second_tour, first_appointment),
    ):
        insort_right(
            tour,
            appointment,
            lo=1,
            hi=len(tour) - 1,
            key=lambda node_id: (node_times[node_id], node_id),
        )


def sample_neighbor(
    problem: ProblemData,
    rng: random.Random,
    tours: Tours,
) -> tuple[Tours, tuple[AgentId, AgentId]] | None:
    """Propose a transfer or swap without modifying the supplied routes.

    Choose two agents and ensure the donor has an appointment when possible.
    If both routes have appointments, use SWAP_PROBABILITY to choose between
    a swap and a transfer. Copy the outer list and only the two changed routes.

    Args:
        problem: Routing data used to maintain appointment order.
        rng: Random generator used to choose agents and the move.
        tours: Routes indexed by agent ID, with home endpoints and interiors
            sorted by scheduled time and node ID.

    Returns:
        Proposed routes and the two changed agent IDs, or None if there are
        fewer than two agents or both selected routes are empty. Unchanged
        route lists are shared with tours. Proposed moves may be infeasible.
    """
    if len(tours) < 2:
        return None

    donor_id, receiver_id = rng.sample(range(len(tours)), k=2)
    if len(tours[donor_id]) <= 2:
        donor_id, receiver_id = receiver_id, donor_id
    if len(tours[donor_id]) <= 2:
        return None

    neighbor = tours.copy()
    donor_tour = tours[donor_id].copy()
    receiver_tour = tours[receiver_id].copy()
    if len(receiver_tour) > 2 and rng.random() < SWAP_PROBABILITY:
        swap_appointments(problem, rng, donor_tour, receiver_tour)
    else:
        give_appointment(problem, rng, donor_tour, receiver_tour)
    neighbor[donor_id] = donor_tour
    neighbor[receiver_id] = receiver_tour

    return neighbor, (donor_id, receiver_id)
