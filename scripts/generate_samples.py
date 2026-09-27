"""Generate synthetic sample problems with real OSRM driving matrices."""

import argparse
import asyncio
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from random import Random

from app.optimization.datamodel import Matrix, Tours
from app.optimization.metrics import calculate_tour_metrics
from app.schemas import AgentInput, AppointmentInput
from app.services.osrm import get_travel_matrices
from app.services.problem_builder import build_problem, input_coordinates
from app.services.samples import SAMPLES

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
AJACCIO_WAVES = ((7, 8), (0, 14), (6, 9), (1, 13), (4, 10), (2, 12), (3, 11), (5,))

# An approximate inset of urban Paris, excluding the two outlying woods.
# Sample throughout this area instead of creating a cluster around each home.
PARIS_OUTLINE = (
    (48.900, 2.319), (48.900, 2.365), (48.887, 2.391),
    (48.871, 2.409), (48.849, 2.410), (48.833, 2.394),
    (48.818, 2.360), (48.817, 2.331), (48.828, 2.292),
    (48.837, 2.264), (48.855, 2.258), (48.877, 2.284),
    (48.894, 2.302),
)


def corsica_nurses() -> tuple[list[AgentInput], list[AppointmentInput]]:
    """Create the deterministic Ajaccio nursing inputs with overlapping visits.

    Returns:
        Two nurses working 08:00-20:00 and 15 patient visits arranged into
        seven simultaneous pairs and one final visit across shared neighborhoods.
        Coordinates and appointment times are synthetic; no routing is fetched.
    """
    agents = [
        AgentInput(
            name=name, latitude=latitude, longitude=longitude,
            start_time=8 * 3600, end_time=20 * 3600,
        )
        for name, latitude, longitude in [
            ("Camille Santoni", 41.9275, 8.7350),
            ("Julien Moretti", 41.9190, 8.7270),
        ]
    ]
    coordinates = [
        (41.9168, 8.7352), (41.9184, 8.7387), (41.9218, 8.7373),
        (41.9249, 8.7358), (41.9275, 8.7333), (41.9307, 8.7338),
        (41.9343, 8.7359), (41.9384, 8.7433), (41.9375, 8.7490),
        (41.9330, 8.7435), (41.9292, 8.7374), (41.9250, 8.7300),
        (41.9217, 8.7281), (41.9182, 8.7240), (41.9158, 8.7175),
    ]
    wave_by_appointment = {
        appointment: wave
        for wave, pair in enumerate(AJACCIO_WAVES)
        for appointment in pair
    }
    appointments = [
        AppointmentInput(
            latitude=latitude, longitude=longitude,
            time=8 * 3600 + 30 * 60 + wave_by_appointment[index] * 75 * 60,
            duration=(35, 45, 55, 40, 50)[index % 5] * 60,
            gain=(30, 45, 35, 50, 40)[index % 5],
        )
        for index, (latitude, longitude) in enumerate(coordinates)
    ]
    return agents, appointments


def paris_deliveries() -> tuple[list[AgentInput], list[AppointmentInput]]:
    """Create the original clustered Paris lunch-delivery inputs.

    Returns:
        Eight couriers working 11:00-15:00 and 80 deliveries in ten waves of
        eight simultaneous appointments. A fixed random seed makes generated
        coordinates, durations, and gains reproducible.
    """
    rng = Random(20260927)
    bases = [
        (48.8705, 2.3265), (48.8785, 2.3335),
        (48.8680, 2.3435), (48.8780, 2.3525),
        (48.8675, 2.3620), (48.8765, 2.3700),
        (48.8670, 2.3795), (48.8595, 2.3695),
    ]
    names = [
        "Léa Martin", "Thomas Bernard", "Inès Dubois", "Hugo Laurent",
        "Chloé Petit", "Louis Moreau", "Sarah Girard", "Adam Fontaine",
    ]
    agents = [
        AgentInput(
            name=name, latitude=latitude, longitude=longitude,
            start_time=11 * 3600, end_time=15 * 3600,
        )
        for name, (latitude, longitude) in zip(names, bases, strict=True)
    ]
    # Eight simultaneous drop-offs per wave keep all eight couriers occupied.
    # Full waves bound the DP state space, even with many successive waves.
    appointments = [
        AppointmentInput(
            latitude=round(latitude + rng.uniform(-0.002, 0.002), 6),
            longitude=round(longitude + rng.uniform(-0.003, 0.003), 6),
            time=11 * 3600 + 30 * 60 + wave * 20 * 60,
            duration=rng.choice((3, 4, 5)) * 60,
            gain=rng.randint(5, 12),
        )
        for wave in range(10)
        for latitude, longitude in bases
    ]
    return agents, appointments


def _paris_coordinate(rng: Random) -> tuple[float, float]:
    """Sample a coordinate inside the approximate urban Paris polygon.

    Reject points outside PARIS_OUTLINE using a ray-crossing polygon test.
    Sampling is uniform in latitude/longitude within the polygon before rounding.

    Args:
        rng: Random generator advanced while sampling candidate coordinates.

    Returns:
        Latitude and longitude rounded to six decimal places.
    """
    while True:
        latitude = rng.uniform(48.817, 48.900)
        longitude = rng.uniform(2.258, 2.410)
        inside = False
        for (lat_a, lon_a), (lat_b, lon_b) in zip(
            PARIS_OUTLINE, (*PARIS_OUTLINE[1:], PARIS_OUTLINE[0]), strict=True,
        ):
            if (lat_a > latitude) != (lat_b > latitude):
                crossing = lon_a + (latitude - lat_a) * (lon_b - lon_a) / (lat_b - lat_a)
                if longitude < crossing:
                    inside = not inside
        if inside:
            return round(latitude, 6), round(longitude, 6)


def paris_dinner_deliveries() -> tuple[list[AgentInput], list[AppointmentInput]]:
    """Create reproducible dinner-delivery locations throughout urban Paris.

    Returns:
        Thirty couriers working 18:00-23:30 and 300 deliveries with seeded
        locations, durations, and gains. Appointment times are placeholders;
        schedule_dinner_deliveries sets them after travel times are available.
    """
    rng = Random(20260928)
    agents = []
    for index in range(30):
        latitude, longitude = _paris_coordinate(rng)
        agents.append(AgentInput(
            name=f"Courier {index + 1:02d}", latitude=latitude, longitude=longitude,
            start_time=18 * 3600, end_time=23 * 3600 + 30 * 60,
        ))
    appointments = []
    for _ in range(300):
        latitude, longitude = _paris_coordinate(rng)
        appointments.append(AppointmentInput(
            latitude=latitude, longitude=longitude,
            # Final times are set using actual travel times after routing.
            time=18 * 3600, duration=rng.randint(2, 5) * 60, gain=rng.randint(6, 18),
        ))
    return agents, appointments


def schedule_dinner_deliveries(
    agents: list[AgentInput],
    appointments: list[AppointmentInput],
    travel_times: Matrix[int],
) -> tuple[list[AppointmentInput], Tours]:
    """Construct dinner appointment times around a feasible reference assignment.

    In ten rounds, assign each courier one of the 30 nearest remaining stops,
    using seeded random choices. Set each appointment no earlier than its
    reference arrival, with staggered targets and extra minute-scale slack.
    The resulting assignment is feasible, not proven optimal.

    Args:
        agents: Couriers with home nodes ordered first in the travel matrix.
        appointments: Exactly ten appointments per agent, ordered after homes
            in the matrix. Input objects are preserved when times are replaced.
        travel_times: Directed travel times in seconds for homes and stops.

    Returns:
        Newly scheduled appointment inputs in original order and reference
        tours indexed by agent, including both home endpoints.

    Raises:
        ValueError: A reference route cannot return home before its workday ends.
    """
    rng = Random(20260929)
    agent_count = len(agents)
    pending = set(range(agent_count, agent_count + len(appointments)))
    scheduled = appointments.copy()
    tours = [[agent] for agent in range(agent_count)]
    departure_times = [agent.start_time for agent in agents]
    for round_index in range(10):
        agent_order = list(range(agent_count))
        rng.shuffle(agent_order)
        for agent in agent_order:
            previous = tours[agent][-1]
            # Random walks among nearby destinations produce crossing routes,
            # while avoiding an excessively long cross-city trip at every stop.
            candidates = sorted(pending, key=lambda node: (travel_times[previous][node], node))[:30]
            node = rng.choice(candidates)
            appointment = appointments[node - agent_count]
            arrival = departure_times[agent] + travel_times[previous][node]
            target = agents[agent].start_time + (15 + round_index * 27 + rng.randint(-7, 7)) * 60
            scheduled_time = ((max(arrival, target) + 59) // 60 + rng.randint(0, 3)) * 60
            scheduled[node - agent_count] = appointment.model_copy(update={"time": scheduled_time})
            departure_times[agent] = scheduled_time + appointment.duration
            tours[agent].append(node)
            pending.remove(node)
    for agent, tour in enumerate(tours):
        if departure_times[agent] + travel_times[tour[-1]][agent] > agents[agent].end_time:
            raise ValueError(f"Generated dinner schedule exceeds the workday for agent {agent}")
        tour.append(agent)
    return scheduled, tours


GENERATORS = {
    "corsica_nurses": corsica_nurses,
    "paris_deliveries": paris_deliveries,
    "paris_dinner_deliveries": paris_dinner_deliveries,
}


async def generate(sample_id: str, output_directory: Path, overwrite: bool) -> None:
    """Generate a sample, fetch real driving matrices, and write its dataset.

    Validate any planted reference tours before writing them as metadata.
    Output uses the catalog filename and gzip compression when it ends in .gz.
    Reference assignments are saved for verification, not supplied to solvers.

    Args:
        sample_id: Identifier supported by GENERATORS and the sample catalog.
        output_directory: Directory to create or reuse for the saved dataset.
        overwrite: Whether an existing dataset may be replaced.

    Raises:
        FileExistsError: The target exists and overwrite is false.
        KeyError: sample_id is not a supported generated sample.
        ValueError: A generated reference route is late or returns home late.
        RoutingServiceError: Driving matrices cannot be obtained from OSRM.
        OSError: The output directory or dataset cannot be written.
    """
    filepath = output_directory / SAMPLES[sample_id][0]
    if filepath.exists() and not overwrite:
        raise FileExistsError(f"{filepath} already exists; use --overwrite to regenerate")
    agents, appointments = GENERATORS[sample_id]()
    print(f"Fetching routing matrices for {sample_id}: {len(agents) + len(appointments)} locations", flush=True)
    distances, travel_times = await get_travel_matrices(input_coordinates(agents, appointments))
    reference_tours = None
    if sample_id == "paris_dinner_deliveries":
        appointments, reference_tours = schedule_dinner_deliveries(agents, appointments, travel_times)
    elif sample_id == "corsica_nurses":
        reference_tours = [
            [agent, *(len(agents) + pair[agent] for pair in AJACCIO_WAVES if agent < len(pair)), agent]
            for agent in range(len(agents))
        ]
    if reference_tours is not None:
        problem = build_problem(agents, appointments, distances, travel_times)
        for agent, tour in enumerate(reference_tours):
            metrics = calculate_tour_metrics(problem, agent, tour)
            if metrics.lateness or metrics.overtime:
                raise ValueError(f"Generated schedule is infeasible for agent {agent}")
    payload = {
        "metadata": {
            "synthetic": True,
            "routing": "OSRM driving; distances in metres, times in seconds",
            "attribution": "Routing by OSRM, map data © OpenStreetMap contributors",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "notes": SAMPLES[sample_id][2],
        },
        "agents": [
            {"name": agent.name, "startTime": agent.start_time, "endTime": agent.end_time, "id": index}
            for index, agent in enumerate(agents)
        ],
        "nodes": [
            {
                "lat": agent.latitude, "lng": agent.longitude, "time": 0, "duration": 0,
                "type": "home", "id": index, "agent_id": index, "gain": 0,
            }
            for index, agent in enumerate(agents)
        ] + [
            {
                "lat": appointment.latitude, "lng": appointment.longitude,
                "time": appointment.time, "duration": appointment.duration,
                "type": "appointment", "id": len(agents) + index,
                "agent_id": None, "gain": appointment.gain,
            }
            for index, appointment in enumerate(appointments)
        ],
        "D": distances,
        "T": travel_times,
    }
    if reference_tours is not None:
        payload["metadata"]["reference_tours"] = reference_tours
    # Match the original sample's compact, one-record / one-matrix-row layout.
    sections = []
    for key, value in payload.items():
        if isinstance(value, list):
            rows = ",\n".join("\t\t" + json.dumps(row, ensure_ascii=False) for row in value)
            sections.append(f'\t"{key}": [\n{rows}\n\t]')
        else:
            sections.append(f'\t"{key}": ' + json.dumps(value, ensure_ascii=False))
    output_directory.mkdir(parents=True, exist_ok=True)
    text = "{\n" + ",\n".join(sections) + "\n}\n"
    if filepath.suffix == ".gz":
        filepath.write_bytes(gzip.compress(text.encode("utf-8"), mtime=0))
    else:
        filepath.write_text(text, encoding="utf-8")
    print(f"Created {filepath}: {len(agents)} agents, {len(appointments)} appointments")


async def main() -> None:
    """Parse generation options and write the selected samples sequentially."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", choices=[*GENERATORS, "all"], default="all", nargs="?")
    parser.add_argument("--output", type=Path, default=DATA_DIRECTORY)
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args()
    sample_ids = GENERATORS if arguments.sample == "all" else [arguments.sample]
    for sample_id in sample_ids:
        await generate(sample_id, arguments.output, arguments.overwrite)


if __name__ == "__main__":
    asyncio.run(main())
