# MTSPA 26

A routing application for assigning fixed-time appointments to multiple agents.
It includes an exact dynamic-programming solver, a simulated-annealing solver,
and a map-based web interface.

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

Open <http://localhost:5173>. Click the map to place agents and appointments,
or find their coordinates by entering an address, then select a solver and
optimize the tours. Use **Load sample data** to populate the editor from
`data/data.json` immediately.

Simulated annealing can optimize one or several loss configs at once. Each
selected config is run in the same process pool, and the result tabs switch
the metrics and map between the proposed solutions.
Dynamic programming supports the Shortest distance and Maximum uptime
configs, either individually or together in one shared state traversal.

Loss-config terms are dimensionless importance values. Before solving a
problem, the backend uses a deterministic sample of appointment-transfer
neighbors to estimate each metric's typical change. It then converts the
importances into fixed problem-specific coefficients, keeping total distance
at weight 1. The same resolved coefficients are reused across every selected
config and parallel run.

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

## Repository structure

```text
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
