# MTSPA

A routing application for assigning fixed-time appointments to multiple agents.
It includes an exact dynamic-programming solver, a simulated-annealing solver,
and a map-based web interface.

## Try it with an AI agent

The [MTSPA routing skill](.agents/skills/mtspa-routing/SKILL.md) lets a local
AI agent run the existing solvers and explain their results. It adds no solver
code, server, or MCP dependency. The default demo uses the synthetic Ajaccio
dataset: two nurses and 15 visits.

### Option 1: open the repository in Codex

Prerequisites: [Git](https://git-scm.com/downloads),
[uv](https://docs.astral.sh/uv/getting-started/installation/), and Codex CLI or
the IDE extension. No separate Python installation is needed if uv's automatic
Python downloads are enabled.

```bash
git clone https://github.com/MatPerr/mtspa.git
cd mtspa
uv sync --locked
```

Open this folder in Codex, or run `codex` here if using the CLI. Codex discovers
the repo-local skill in `.agents/skills` automatically
([official documentation](https://learn.chatgpt.com/docs/build-skills)). Ask:

```text
Use $mtspa-routing to compare DP and simulated annealing on the Ajaccio sample.
Show distance, runtime, lateness, and overtime, and generate the DP route SVG.
```

The demo needs neither the frontend nor an API server, and requires no additional
API key. Initial setup downloads dependencies; optimization uses the saved
travel matrices without calling OSRM or Photon. Your AI agent's own account
and usage requirements still apply.

### Option 2: install just the skill from Codex

Paste this into Codex; it is a prompt, not a shell command:

```text
$skill-installer install https://github.com/MatPerr/mtspa/tree/main/.agents/skills/mtspa-routing
```

On the next turn, use the same `$mtspa-routing` prompt above. If the skill does
not appear, restart Codex. The standalone skill contains instructions, not the
solver package: on first use it will reuse a checkout or clone the repository
and run `uv sync --locked`. Git, uv, and local shell access are still required.
Choose either installation method; both are not necessary. For another agent
with shell access, point it directly at the skill's `SKILL.md` and ask it to
follow the instructions; automatic discovery depends on the agent.

### Try the same demo without an AI agent

From the cloned repository:

```bash
uv run python -m scripts.compare data/corsica_nurses.json --steps 50000 --runs 2 --seed 0 --no-progress
uv run python -m app.optimization.solvers.dp data/corsica_nurses.json --max-states 200000 --output artifacts/interview-dp
```

Open `artifacts/interview-dp/dp_shortest_distance_tours.svg` in a browser. Its JSON
summary is saved beside it. Repeating the same solver and objective replaces
their two report files; choose another `--output` directory to preserve a run.

### Use your own agents and appointments

The skill also accepts manual data from a conversation, table, CSV, or JSON.
Provide each agent's home address or coordinates and working hours, plus each
appointment's location, fixed time, duration, and gain. The agent will ask about
missing details, resolve addresses with Photon when needed, and obtain driving
matrices from OSRM before running the existing solvers. No web app is required.
Address queries go to Photon; coordinates go to OSRM. Manual files and reports
stay in the ignored `artifacts/` directory unless you choose another location.

```text
Use $mtspa-routing to optimize the agents and appointments in my attached CSV.
Ask me for missing information and confirm any ambiguous addresses.
```

The [manual-data guide](.agents/skills/mtspa-routing/references/manual-data.md)
includes the input schema and a runnable dataset-preparation recipe.

## Setup

The backend requires Python 3.14 and uses `uv`. The frontend uses React,
TypeScript, Vite, MUI, Leaflet, and `pnpm`.

```bash
uv sync
pnpm --dir frontend install
```

## Run the web application

Start the API:

```bash
uv run uvicorn app.main:app --reload
```

In another terminal, start the frontend:

```bash
pnpm --dir frontend dev
```

Open <http://localhost:5173>. Choose **Sample data** and select a dataset to load
it immediately, or choose **Manual data** to add agents and appointments using
the map or an address. The two modes keep their data separately, so switching
between them preserves manual entries. The **Nodes** list starts collapsed.
Select a solver and optimize the tours.

Simulated annealing can optimize one or several loss configs at once. Each
selected config is run in the same process pool, and the result tabs switch
the metrics and map between the proposed solutions.
Dynamic programming supports the Shortest distance and Maximum uptime
configs, either individually or together in one shared state traversal.

Simulated annealing tries both appointment transfers and swaps. Swaps prefer
appointments at the same time, which helps improve fully occupied schedules
without introducing simultaneous appointments for one agent.

Each `LossConfig` stores metadata and an `importances` dictionary keyed by
metric name. Before solving a
problem, the backend uses a deterministic sample of transfer and swap
neighbors to estimate each metric's typical change. It then converts the
importances into a plain dictionary of fixed weights, keeping total distance
at weight 1 for the built-in configs. Selected configs share one calibration
walk; each config's weights are reused across its parallel runs.

```python
from app.optimization.loss_calibration import calibrate_loss_weights
from app.optimization.objectives import LOSS_CONFIGS, calculate_loss

config = LOSS_CONFIGS["shortest_distance"]
weights = calibrate_loss_weights(problem, config.importances)
loss = calculate_loss(solution_metrics, weights)
```

The calibration formula is `weight = importance * distance_scale / metric_scale`.
Solvers keep `loss_config` for its metadata and `weights` for scoring; no
separate resolved-config or term objects are needed.

The backend currently requests distance and driving-time matrices from the
public OSRM server. Set `OSRM_BASE_URL` to select another OSRM instance:

```bash
OSRM_BASE_URL=https://router.project-osrm.org \
  uv run uvicorn app.main:app --reload
```

Address autocomplete uses the public Photon demo service through the backend.
Its base URL and identifying user agent can be changed with `PHOTON_BASE_URL`
and `PHOTON_USER_AGENT`. Requests start after three characters, are debounced
in the browser, and are cached in memory by the backend.

## Command-line solvers

```bash
uv run python -m app.optimization.solvers.dp
uv run python -m app.optimization.solvers.dp --loss-config maximum_uptime
uv run python -m app.optimization.solvers.sa
uv run python -m app.optimization.solvers.sa --loss-config fair_hourly_pay
uv run python -m scripts.compare
```

The default input is `data/data.json`. Distances are expressed in metres and
travel times in seconds.

### Minimal solvers

To focus on the algorithms without app callbacks, convergence history, multiple
objectives, or report exports, run the lite modules from the repository root:

```bash
uv run python -m app.optimization.solvers.dp_lite
uv run python -m app.optimization.solvers.sa_lite --steps 50000 --runs 2 --seed 0
```

Both accept an optional dataset path and print runtime, loss, distance, lateness,
overtime, and every agent's route. Their CLI uses the default Shortest distance
objective. DP accepts `--max-states` (default: 8 million). SA retains the changed-tour
metrics cache and parallel independent runs: tqdm counts steps for a single run
and completed runs for parallel execution. Use `--no-progress` to hide it. Runtime
covers all runs, not just the winning one; loading and loss calibration are excluded.

The agent skill uses the full CLIs in `app/optimization/solvers/dp.py` and `sa.py`
(their `main()` functions) to obtain JSON/SVG reports. `scripts/compare.py` provides
the comparison CLI. The skill instructs agents to show each agent's route and
embed report images in chat, using PNG previews when SVG display is unavailable.

### Exported reports

Both solver CLIs write JSON and SVG reports to `artifacts/`, or the directory
selected with `--output`. Filenames include the solver and selected loss config:
`dp_maximum_uptime_summary.json`, `dp_maximum_uptime_tours.svg`,
`sa_fair_distance_summary.json`, and `sa_fair_distance_tours.svg`, for example.
Different solvers/configs coexist; rerunning the same pair replaces its files.
The comparison command only prints its table and routes; run a solver CLI to
generate report files.

Both JSON reports use the same schema: solver/method, objective metadata and
calibrated weights, loss, runtime, run settings, timing feasibility, complete
`SolutionMetrics` under `metrics`, and complete `TourMetrics` under each
`agents[agent_id].metrics`, alongside names and route node IDs. Units are included.
DP records its state limit and final state count; SA records steps per run, run
count, and the input seed. SA exports the best solution across all runs, while
runtime covers all runs. Runtime excludes loading, loss-weight calibration and
report writing, but includes SA's temperature calibration.

SVG titles identify the actual objective and exact/approximate method. Routes
are straight geographic connections, not road geometry; lateness and overtime
remain visible for potentially infeasible SA results.

## Sample datasets

| Dataset | Agents | Appointments | Working hours |
| --- | ---: | ---: | --- |
| `data/data.json` — Belgium - real estate agents | 7 | 21 | 08:00–20:00 |
| `data/corsica_nurses.json` — Ajaccio - nurses | 2 | 15 | 08:00–20:00 |
| `data/paris_deliveries.json` — Paris - trivial lunch deliveries | 8 | 80 | 11:00–15:00 |
| `data/paris_dinner_deliveries.json.gz` — Paris - difficult dinner deliveries | 30 | 300 | 18:00–23:30 |

The Belgium sample's home locations have independent random offsets of roughly
100–300 metres; appointment locations are unchanged. Its saved distance and
travel-time matrices were recomputed with OSRM for the shifted locations.
Location perturbation is not a guarantee of anonymity.

The new examples are synthetic: names, visit locations, schedules, and payments
do not represent real nurses, patients, couriers, or orders. They contain saved
[OSRM driving matrices](https://project-osrm.org/docs/v5.24.0/api/#table-service),
using © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) data.
The web application requests fresh matrices when solving; the CLI uses the
saved matrices. Neither models live traffic. The Paris examples model scheduled
drop-offs, not restaurant pickups, vehicle capacity, or cycling routes.

Ajaccio has 35–55 minute visits from 08:30 to 17:15. Seven pairs of simultaneous
visits force both nurses into the same neighborhoods, with repeated journeys
across town. Assigning patients to the nearest nurse's home causes lateness.
This example remains small enough for both SA and DP.

The original Paris lunch dataset is preserved, with a new label in the selector.
It has ten waves of eight simultaneous deliveries, every 20 minutes from 11:30
to 14:30, with 3–5 minute handovers. Both SA and DP support this example.

The difficult dinner dataset spreads 30 homes and 300 stops across urban Paris,
on both banks of the Seine. Its staggered appointment times are derived from
real driving times along crossing reference routes, with 2–5 minute handovers.
It has a verified on-time solution, but assigning each stop to its nearest home
does not produce a feasible schedule. Use SA for this dataset; 30 agents are
beyond the practical scope of this DP implementation.

The two harder datasets include feasible `reference_tours` in their metadata
for validation. These assignments are not supplied to either solver. The dinner
file is gzip-compressed to keep its 330-by-330 matrices small; the loader and CLI
read `.json.gz` directly. The web app assembles large matrices from smaller OSRM
table requests, with at most two requests in flight.

There is no universal maximum number of appointments for DP: timing and agent
count determine how many states survive. The Paris lunch waves deliberately keep
this larger example tractable. Every complete wave uses all eight agents,
so a partial wave has at most `8! × C(8, 4) = 2,822,400` states, below the
8-million limit. Nine agents with the same fully connected wave structure
could require `9! × C(9, 4) = 45,722,880` states. The bound concerns one state
layer, not RAM bytes; DP can hold two layers simultaneously.

A local check of both DP loss configs together on the saved Paris lunch matrices
took about 8 minutes 48 seconds, with 2,822,400 peak states, 40,320 final
states, and roughly 2.4 GiB peak process memory. Both results had zero lateness
and overtime. This is a stress-test sample; runtime depends on your machine.

```bash
uv run python -m app.optimization.solvers.dp data/corsica_nurses.json
uv run python -m app.optimization.solvers.dp data/paris_deliveries.json
uv run python -m app.optimization.solvers.sa data/paris_dinner_deliveries.json.gz
```

To regenerate either harder dataset while preserving the original Paris lunch
file (requests public OSRM tables; results can change when routing data changes):

```bash
uv run python -m scripts.generate_samples corsica_nurses --overwrite
uv run python -m scripts.generate_samples paris_dinner_deliveries --overwrite
```

## Repository structure

```text
.agents/skills/mtspa-routing/  Installable agent instructions (no solver duplication)
app/
  main.py                  FastAPI endpoints
  schemas.py               HTTP request and response models
  optimization/            Domain models, metrics, reports, and solvers
  services/                OSRM and problem construction
frontend/                  React map and problem editor
scripts/                   Command-line comparison tools
data/                      Sample problem data
```

The backend is stateless: the frontend sends the complete problem to
`POST /api/solve`, or to `POST /api/solve-stream` for live solver status.
The API requests `D` and `T` from OSRM and passes the constructed
`ProblemData` to the selected solver.

## Checks

```bash
uv run pre-commit run --all-files
pnpm --dir frontend build
```
