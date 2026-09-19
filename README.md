# MTSPA 26

A small routing-optimization project comparing two approaches:

- `DynamicProgrammingSolver` finds the exact minimum-distance solution while
  enforcing appointment and end-of-day feasibility.
- `SimulatedAnnealingSolver` searches approximately using distance plus a
  lateness penalty.

## Setup

The project requires Python 3.14 and uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

## Run

```bash
uv run python DP.py
uv run python SA.py
uv run python compare.py
```

The comparison script accepts options such as:

```bash
uv run python compare.py --steps 100000 --runs 4 --seed 42
```

Use `--help` on any script to see its available arguments.

The default input is `data/data.json`. Distances are expressed in metres and
travel times in seconds.

## Checks

```bash
uv run pre-commit run --all-files
```
