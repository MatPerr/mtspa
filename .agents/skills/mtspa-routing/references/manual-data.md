# Prepare manual routing data

Use this workflow for user-provided agents and appointments without saved
distance/time matrices. Run the examples from an MTSPA checkout after
`uv sync --locked`. Reuse the existing helpers; no server or frontend is needed.

## 1. Collect and normalize inputs

- Each agent needs a name, home location, and workday start/end.
- Each appointment needs a location, fixed scheduled time, service duration,
  and nonnegative integer gain. Use consistent monetary units across visits.
- Ask for missing values. If gains are irrelevant, propose zero gains and get
  agreement rather than silently filling them in. Do not default an unknown
  service duration to zero.
- Convert clock times to integer seconds from midnight (`08:30` is `30600`),
  and service durations to seconds. This is a single-day, fixed-time model;
  overnight shifts and flexible time windows are not supported. Do not silently
  choose the midpoint of a time window.
- Use driving travel times. If the user needs walking, cycling, pickup-before-
  delivery, or capacity constraints, explain that this workflow does not model
  them rather than claiming the resulting routes satisfy them.

Explain before network calls that address text is sent to public Photon and
coordinates to public OSRM; names, payments, and schedules are not sent to those
services. If external sharing is not acceptable, use user-provided matrices or
approved service instances via `PHOTON_BASE_URL` and `OSRM_BASE_URL` instead.

Resolve addresses as described below, then save normalized inputs to an unused
path such as `artifacts/manual/input.json`. This directory is already ignored by
Git. Keep real input files and reports out of commits unless explicitly asked.
The JSON uses `latitude`/`longitude` and snake_case times, **not** the saved
dataset's `lat`/`lng` and `startTime`/`endTime` keys. IDs are assigned later.

This small Paris example is illustrative; replace it with the user's data:

```json
{
  "agents": [
    {"name": "Camille", "latitude": 48.8566, "longitude": 2.3522, "start_time": 28800, "end_time": 61200},
    {"name": "Julien", "latitude": 48.8642, "longitude": 2.3359, "start_time": 28800, "end_time": 61200}
  ],
  "appointments": [
    {"latitude": 48.8606, "longitude": 2.3376, "time": 32400, "duration": 1800, "gain": 30},
    {"latitude": 48.8534, "longitude": 2.3488, "time": 36000, "duration": 1800, "gain": 40}
  ]
}
```

Validate against `AgentInput` and `AppointmentInput` in `app/schemas.py` using
the recipe below. Do not pass extra requested constraints as arbitrary JSON
fields: the schemas can ignore unknown keys, and that does not implement them.

## 2. Resolve addresses when necessary

Skip this step for supplied coordinates. For an address, use the existing
`search_addresses` helper with city/postcode/country context. For example:

```bash
uv run python - <<'PY'
import asyncio
import json
from dataclasses import asdict

from app.services.geocoding import search_addresses

suggestions = asyncio.run(search_addresses("Place de l'Hôtel de Ville, Paris, France", limit=5))
print(json.dumps([asdict(item) for item in suggestions], ensure_ascii=False, indent=2))
PY
```

Inspect the returned labels and coordinates. Ask the user to choose when results
are ambiguous; do not blindly select the first suggestion. For no match, ask for
a more precise address or coordinates. Resolve each distinct address once and
record the chosen location in the input JSON. Helper output uses latitude first;
do not manually reverse it to match Photon's underlying GeoJSON representation.

## 3. Fetch matrices and save a validated dataset

Create the input JSON with the available file-editing tools, then run this recipe.
Change the two paths together if using a different directory. It validates all
inputs before contacting OSRM, assigns IDs with `build_problem`, and preserves
matrix row/column order. The output must not already exist.

```bash
uv run python - <<'PY'
import asyncio
import json
from pathlib import Path

from app.optimization.datamodel import ProblemData
from app.optimization.problem_io import load_data
from app.schemas import SampleProblemResponse
from app.services.osrm import get_travel_matrices
from app.services.problem_builder import build_problem, input_coordinates

source = Path("artifacts/manual/input.json")
target = Path("artifacts/manual/data.json")
if target.exists():
    raise FileExistsError(f"Choose an unused output path: {target}")
inputs = SampleProblemResponse.model_validate_json(source.read_text(encoding="utf-8"), strict=True)
if not inputs.agents or not inputs.appointments:
    raise ValueError("At least one agent and one appointment are required")

coordinates = input_coordinates(inputs.agents, inputs.appointments)
distances, travel_times = asyncio.run(get_travel_matrices(coordinates))
problem = build_problem(inputs.agents, inputs.appointments, distances, travel_times)
payload = {
    "metadata": {
        "routing": "OSRM driving; distances in metres, times in seconds",
        "attribution": "Routing by OSRM, map data © OpenStreetMap contributors",
    },
    "agents": [
        {"id": agent.id, "name": agent.name, "startTime": agent.start_time, "endTime": agent.end_time}
        for agent in problem.agents
    ],
    "nodes": [
        {
            "id": node.id, "lat": node.latitude, "lng": node.longitude,
            "time": node.time, "duration": node.duration, "type": node.kind,
            "agent_id": node.agent_id, "gain": node.gain,
        }
        for node in problem.nodes
    ],
    "D": problem.distances,
    "T": problem.travel_times,
}
with target.open("x", encoding="utf-8") as output:
    json.dump(payload, output, ensure_ascii=False, indent=2)
    output.write("\n")
ProblemData(*load_data(target))
print(f"Saved {target}: {len(problem.agents)} agents, {len(problem.appointment_ids)} appointments")
PY
```

`input_coordinates` puts agent homes first, in agent order, then appointments in
input order. `build_problem` uses precisely that same order. Do not reorder one
without the other, symmetrize the directed matrices, or replace missing routes
with zero. Distances are integer metres; driving times are integer seconds.

If validation fails, explain the specific missing/invalid input and correct it
with the user before retrying. If Photon or OSRM fails or a route is unreachable,
report the failure; do not fabricate coordinates or matrices. Reuse a saved
dataset for repeated optimizations. Changing coordinates or node order/count
requires fresh or correctly reindexed matrices; changing only schedules or gains
does not require another routing request.

## 4. Run the existing solvers

For a small problem and a DP-supported objective, start with a bounded exact run:

```bash
uv run python -m app.optimization.solvers.dp artifacts/manual/data.json --max-states 200000 --output artifacts/manual/dp
```

Use an unused report directory; repeating a solver/config overwrites its report
files. A state-budget failure is not proof of infeasibility. Respect the
user's requested solver/objective and resource budget, as described in
[SKILL.md](../SKILL.md).

SA requires at least two agents. With one agent, explain this restriction and
offer DP; do not duplicate the agent to satisfy the check. For at least two:

```bash
uv run python -m app.optimization.solvers.sa artifacts/manual/data.json \
  --steps 50000 --runs 2 --seed 0 --output artifacts/manual/sa
```

For a small problem with at least two agents, the comparison CLI also accepts
the saved file:

```bash
uv run python -m scripts.compare artifacts/manual/data.json --steps 50000 --runs 2 --seed 0 --no-progress
```

It uses the default shortest-distance objective and the default DP state limit,
not `200000`.

Both commands export `<solver>_<loss_config>_summary.json` and
`<solver>_<loss_config>_tours.svg`. These examples use `dp_shortest_distance` and
`sa_shortest_distance`. Read the JSON's complete `metrics` and per-agent
`agents[id].metrics`; report lateness and overtime alongside distance and runtime,
display every agent's route and the route image in chat as instructed in
[SKILL.md](../SKILL.md), and link both generated reports. Home node IDs equal agent IDs for this
workflow; appointment node IDs start after the homes. When mapping routes back
to user labels, distinguish node IDs from zero-based appointment indices.
