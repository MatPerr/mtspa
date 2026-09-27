---
name: mtspa-routing
description: "Run MTSPA's exact dynamic-programming and simulated-annealing route solvers on bundled samples or saved MTSPA datasets. Use to assign fixed-time appointments to agents, compare route quality and runtime, or demonstrate the routing algorithms. Not for general travel planning or modifying the solver implementation."
---

# MTSPA routing

Use the existing Python solvers in https://github.com/MatPerr/mtspa_26.
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
   git clone --depth 1 https://github.com/MatPerr/mtspa_26.git mtspa_26
   cd mtspa_26
   ```

   Reuse existing checkouts without resetting changes or pulling automatically.
3. From the repository root, run `uv sync --locked`. The project pins Python
   3.14; uv can download it if needed. If Git or uv is unavailable, report the
   missing prerequisite instead of installing system tools without direction.

Run all commands below from that repository root. Setup needs network access;
subsequent solves on bundled data use saved matrices without OSRM requests.
No frontend, API server, Node.js, or additional API key is required.

## Quick interview demo

Unless the user specifies a dataset, use `data/corsica_nurses.json`: two agents,
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

Read and link the generated `optimal_distance_summary.json` and
`optimal_distance_tours.svg` files. The SVG shows geographic connections,
not road-following geometry. Do not start the web app unless requested.

## Other datasets and objectives

- `data/data.json`: original Belgium example, seven agents and 21 appointments.
- `data/paris_deliveries.json`: eight agents and 80 visits. DP is a stress test
  that can take minutes and several GiB; do not use it as the default demo.
- `data/paris_dinner_deliveries.json.gz`: 30 agents and 300 visits. Use SA,
  not DP. Start with a bounded run before attempting a large benchmark.

For SA alone, or to choose an objective:

```bash
uv run python -m app.optimization.solvers.sa data/corsica_nurses.json --steps 50000 --runs 2 --seed 0 --loss-config fair_hourly_pay
```

SA accepts `shortest_distance`, `fair_hourly_pay`, `fair_distance`, and
`maximum_uptime`. DP accepts only `shortest_distance` and `maximum_uptime`,
selected with its `--loss-config` option. The comparison command uses the
default shortest-distance objective and has no loss-config option.
For maximum-uptime DP, report the selected objective explicitly: the export's
filenames and JSON objective label are currently distance-oriented.

Respect the requested steps, runs, and DP state budget. A DP state-limit error
does not prove infeasibility; explain it and propose SA or a larger approved
budget instead of silently increasing the limit. Do not claim a universal
maximum problem size for DP.

For a supplied `.json` or `.json.gz` dataset, read
`app/optimization/problem_io.py` and `app/optimization/datamodel.py` to validate
the existing format: `nodes`, `agents`, `D`, and `T`; consecutive zero-based IDs;
one home per agent; matrix rows and columns indexed by node ID. Distances are
metres, travel times and durations are seconds, and appointment/workday times
are seconds from midnight. Never invent travel matrices. If only addresses or
coordinates are supplied, explain that routing data is still needed; the web/API
workflow sends coordinates to public OSRM and address queries to Photon.

## Interpret and present results

- Report the dataset, solver, objective, seed, steps/runs where relevant, and
  measured runtime. Parallel SA runtime is for all runs together, not just the
  winning run; routes and metrics describe the winning solution.
- Summarize distance in km, lateness and overtime in minutes, and relevant
  fairness/waiting metrics. Include per-agent routes or artifact links when useful.
- DP is exact for its supported objective within this fixed-time model and
  requires on-time appointments and return home. SA is approximate and can
  return late/overtime routes; check both totals before describing it as feasible.
  A shorter SA route with lateness is not a feasible improvement over DP.
- Loss weights are calibrated for the dataset. Do not compare raw losses
  across different datasets or loss configs as if they shared a scale.
- These are fixed appointment times, not flexible time windows. Saved driving
  times do not model live traffic. The delivery examples do not model pickups,
  vehicle capacities, or cycling. Do not present them as production guarantees.
