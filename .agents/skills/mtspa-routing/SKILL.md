---
name: mtspa-routing
description: "Run MTSPA's exact dynamic-programming and simulated-annealing route solvers on bundled samples, saved datasets, or user-provided agents and appointments. Use to prepare manual routing data from addresses or coordinates, assign fixed-time appointments, compare route quality and runtime, or demonstrate the algorithms. Not for general travel planning or modifying the solver implementation."
---

# MTSPA routing

Use the existing Python solvers in https://github.com/MatPerr/mtspa.
This is an instruction-only skill: it requires a local shell, Git, and `uv`;
it does not include the solver code or run it remotely.

## Locate and prepare the project

1. Reuse an MTSPA checkout in the current workspace, or the checkout containing
   this skill. Confirm it contains `pyproject.toml` with `name = "mtspa-26"`
   and `app/optimization/solvers/`. Do not assume the skill's installation
   directory contains the rest of the repository.
2. If only the standalone skill is installed, clone the public repository into
   an unused directory in the workspace:

   ```bash
   git clone --depth 1 https://github.com/MatPerr/mtspa.git mtspa
   cd mtspa
   ```

   Reuse existing checkouts without resetting changes or pulling automatically.
3. From the repository root, run `uv sync --locked`. The project pins Python
   3.14; uv can download it if needed. If Git or uv is unavailable, report the
   missing prerequisite instead of installing system tools without direction.

Run all commands below from that repository root. Setup needs network access;
subsequent solves on bundled data use saved matrices without OSRM requests.
No frontend, API server, Node.js, or additional API key is required.

## User-provided agents and appointments

For manual input (conversation, table, CSV, or JSON without travel matrices),
read [Manual data](references/manual-data.md). It provides the required fields,
address-resolution workflow, and a runnable recipe using the existing schemas,
Photon/OSRM clients, and problem builder to save a solver-ready dataset.

Ask for missing locations, working hours, appointment times, durations, or gains;
do not silently invent them. Explain which information goes to external services
before querying them. Resolve ambiguous addresses with the user. Keep personal
inputs and generated reports under the ignored `artifacts/` directory or outside
the repository, and do not publish them without explicit authorization.

## Quick interview demo

For a demo without user-provided data, use `data/corsica_nurses.json`: two agents,
15 fixed-time visits, and an 08:00–20:00 workday. The names and visit locations
are synthetic. Compare both methods using the existing command:

```bash
uv run python -m scripts.compare data/corsica_nurses.json --steps 50000 --runs 2 --seed 0 --no-progress
```

To produce a DP route visualization and JSON summary, choose an unused output
directory; the report writer overwrites its two fixed filenames on repeated runs:

```bash
uv run python -m app.optimization.solvers.dp data/corsica_nurses.json --max-states 200000 --output artifacts/interview-dp
```

Read the generated `dp_shortest_distance_summary.json`, display the routes and
image in chat as described below, and link both it and
`dp_shortest_distance_tours.svg`. The SVG shows geographic connections,
not road-following geometry. Do not start the web app unless requested.

## Other datasets and objectives

- `data/data.json`: original Belgium example, seven agents and 21 appointments.
- `data/paris_deliveries.json`: eight agents and 80 visits. DP is a stress test
  that can take minutes and several GiB; do not use it as the default demo.
- `data/paris_dinner_deliveries.json.gz`: 30 agents and 300 visits. Use SA,
  not DP. Start with a bounded run before attempting a large benchmark.

For SA alone, or to choose an objective:

```bash
uv run python -m app.optimization.solvers.sa data/corsica_nurses.json \
  --steps 50000 --runs 2 --seed 0 --loss-config fair_hourly_pay --output artifacts/interview-sa
```

SA accepts `shortest_distance`, `fair_hourly_pay`, `fair_distance`, and
`maximum_uptime`. DP accepts only `shortest_distance` and `maximum_uptime`,
selected with its `--loss-config` option. The comparison command uses the
default shortest-distance objective and has no loss-config option.

Both solver CLIs export `<solver>_<loss_config>_summary.json` and
`<solver>_<loss_config>_tours.svg` in their `--output` directory (default:
`artifacts/`). For the SA example these start with `sa_fair_hourly_pay`.
Report names and labels reflect the selected objective. Repeating a solver/config
overwrites its two files; use an unused directory to preserve earlier runs.
The comparison CLI prints a table but does not export files itself.

Respect the requested steps, runs, and DP state budget. A DP state-limit error
does not prove infeasibility; explain it and propose SA or a larger approved
budget instead of silently increasing the limit. Do not claim a universal
maximum problem size for DP.

For a supplied `.json` or `.json.gz` dataset, read
`app/optimization/problem_io.py` and `app/optimization/datamodel.py` to validate
the existing format: `nodes`, `agents`, `D`, and `T`; consecutive zero-based IDs;
one home per agent; matrix rows and columns indexed by node ID. Distances are
metres, travel times and durations are seconds, and appointment/workday times
are seconds from midnight. Never invent travel matrices. For missing matrices,
follow [Manual data](references/manual-data.md); no web server is needed.

## Interpret and present results

- Read the JSON report, not just rounded console values. Both solvers export
  complete solution `metrics` and per-agent `agents[id].metrics`, with units,
  calibrated weights in `objective.weights`, loss, runtime, and `run_settings`.
  `timing_feasible` indicates zero lateness and overtime. Link the JSON and SVG.
- Get coordinates directly from `report["nodes"][str(node_id)]`: `latitude`
  and `longitude` are numeric WGS84 decimal degrees, not rounded map positions.
  This mapping includes every home and appointment, plus `id`, `kind`,
  `agent_id`, `time`, `duration`, and `gain`. Resolve each ID in
  `report["agents"][str(agent_id)]["tour"]` through this mapping; no input
  dataset or geocoding request is needed. A home's `agent_id` identifies its
  owner; appointment assignments come from the returned tours. Reports now
  contain location data, so keep personal reports out of public commits.
- Display every agent's route in the chat, not just aggregate metrics or a file
  link: agent name, home → ordered appointments → home, distance, and any
  lateness/overtime. Include agents with no appointments as home → home.
  Use the report's node IDs consistently; do not confuse home IDs, agent IDs,
  or appointment indices. For comparisons, show each solution's routes.
- Display the generated route images inline in the chat, not only as download
  links. If the interface cannot preview SVG, render a PNG preview with an
  available browser or SVG renderer, preserving the original SVG. Inspect the
  preview for clipping and embed it in the final answer, labeled by solver and
  objective. Use the actual report, not a generated illustration. If rendering
  or inline display is unavailable, explain that limitation and provide links
  instead of claiming an image was shown.
- Report the dataset, solver, objective, seed, steps/runs where relevant, and
  measured runtime. Parallel SA runtime is for all runs together, not just the
  winning run; routes and metrics describe the winning solution.
- Summarize distance in km, lateness and overtime in minutes, and relevant
  fairness/waiting metrics alongside the per-agent routes and images.
- DP is exact for its supported objective within this fixed-time model and
  requires on-time appointments and return home. SA is approximate and can
  return late/overtime routes; check both totals before describing it as feasible.
  A shorter SA route with lateness is not a feasible improvement over DP.
- Loss weights are calibrated for the dataset. Do not compare raw losses
  across different datasets or loss configs as if they shared a scale.
- These are fixed appointment times, not flexible time windows. Saved driving
  times do not model live traffic. The delivery examples do not model pickups,
  vehicle capacities, or cycling. Do not present them as production guarantees.
