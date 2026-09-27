from pathlib import Path

from app.optimization.problem_io import load_data
from app.schemas import AgentInput, AppointmentInput, SampleDatasetResponse, SampleProblemResponse

DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "data"
SAMPLES = {
    "belgium": (
        "data.json", "Belgium - real estate agents",
        "Seven agents and 21 appointments: the original routing example in Belgium.",
    ),
    "corsica_nurses": (
        "corsica_nurses.json", "Ajaccio - nurses",
        "Two nurses, 15 overlapping patient visits across Ajaccio, 08:00–20:00. "
        "Both nurses must cover the same neighborhoods. All people and visits are fictional.",
    ),
    "paris_deliveries": (
        "paris_deliveries.json", "Paris - trivial lunch deliveries",
        "Eight couriers, 80 scheduled drop-offs, 11:00–15:00. "
        "Driving times; no restaurant pickups. Larger DP example: allow several minutes and a few GB of RAM.",
    ),
    "paris_dinner_deliveries": (
        "paris_dinner_deliveries.json.gz", "Paris - difficult dinner deliveries",
        "Thirty couriers, 300 staggered drop-offs across Paris, 18:00–23:30. "
        "Use simulated annealing for this large example. Driving times; no restaurant pickups.",
    ),
}


def list_samples() -> list[SampleDatasetResponse]:
    """Build the sample catalog with counts read from the saved datasets.

    Returns:
        Display metadata and agent/appointment counts in catalog order.

    Raises:
        OSError: A catalogued dataset cannot be read.
    """
    samples = []
    for sample_id, (filename, name, description) in SAMPLES.items():
        nodes, agents, _, _ = load_data(DATA_DIRECTORY / filename)
        samples.append(SampleDatasetResponse(
            id=sample_id, name=name, description=description,
            agent_count=len(agents),
            appointment_count=sum(node.kind != "home" for node in nodes),
        ))
    return samples


def load_sample(sample_id: str) -> SampleProblemResponse:
    """Load a catalogued dataset into editable API inputs.

    Resolve filenames through SAMPLES rather than interpreting the supplied
    ID as a path. Saved matrices and reference tours are omitted from the API
    inputs; solving those inputs requests fresh routing matrices.

    Args:
        sample_id: Identifier present in the sample catalog.

    Returns:
        Agents with home coordinates and appointments in their saved ID order.

    Raises:
        KeyError: sample_id is not catalogued or an agent has no saved home.
        OSError: The dataset cannot be read.
    """
    # Only catalogued IDs can resolve to files; never use user input as a path.
    filename, _, _ = SAMPLES[sample_id]
    nodes, agents, _, _ = load_data(DATA_DIRECTORY / filename)
    homes = {node.agent_id: node for node in nodes if node.kind == "home"}
    return SampleProblemResponse(
        agents=[
            AgentInput(
                name=agent.name,
                latitude=homes[agent.id].latitude,
                longitude=homes[agent.id].longitude,
                start_time=agent.start_time,
                end_time=agent.end_time,
            )
            for agent in agents
        ],
        appointments=[
            AppointmentInput(
                latitude=node.latitude, longitude=node.longitude,
                time=node.time, duration=node.duration, gain=node.gain,
            )
            for node in nodes if node.kind != "home"
        ],
    )
