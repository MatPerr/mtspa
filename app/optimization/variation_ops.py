import random
from bisect import insort_right

from app.optimization.datamodel import AgentId, ProblemData, Tour, Tours

SWAP_PROBABILITY = 0.5


def initialize_random_tours(
    problem: ProblemData,
    rng: random.Random,
) -> Tours:
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
