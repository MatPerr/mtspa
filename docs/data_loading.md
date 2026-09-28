# Data loading and problem construction

[Documentation index](README.md)

There are two input paths. Both produce the same `ProblemData`, but only the
editable-input path requests new driving matrices.

## Saved datasets — CLI and bundled samples

Source: [problem_io.py](../app/optimization/problem_io.py).

```text
ProblemData(*load_data(filepath))
├── load_data(filepath)
│   ├── [*.gz] gzip.open(..., encoding="utf-8")
│   ├── [otherwise] Path.open(encoding="utf-8")
│   ├── json.load()
│   ├── [sort nodes and agents by ID; construct Node and Agent records]
│   ├── [convert D and T cells with int(); preserve matrix order]
│   └── [return nodes, agents, distances, travel_times]
└── ProblemData.__post_init__()
    └── [validate structure and precompute solver lookups]
```

| Saved JSON | Python representation | Meaning |
| --- | --- | --- |
| `nodes[].lat`, `lng` | `Node.latitude`, `longitude` | Coordinates in decimal degrees |
| `nodes[].type` | `Node.kind` | `home` or `appointment` |
| `nodes[].time`, `duration`, `gain` | Same names on `Node` | Scheduled time, service duration, gain |
| `nodes[].agent_id` | `Node.agent_id` | Owner of a home; not the optimized assignment |
| `agents[].startTime`, `endTime` | `Agent.start_time`, `end_time` | Seconds from midnight |
| `D`, `T` | `distances`, `travel_times` | Directed metres and driving seconds |

Node and agent IDs must each be consecutive from zero. Matrix entry `[i][j]`
means travel from node `i` to node `j`, regardless of the order of JSON objects.
Sorting objects does **not** reorder the matrices. The loader casts values;
`int()` truncates a fractional numeric value rather than rounding it.
Extra metadata and reference tours are not fed into optimization.

`load_data()` is not a complete input validator. `ProblemData` checks structural
invariants, but does not apply all the coordinate, workday, or value bounds of
the API schemas. See [data model](datamodel.md#validation-and-precomputation).

## Editable agents and appointments — API or manual preparation

Sources: [schemas.py](../app/schemas.py),
[problem_builder.py](../app/services/problem_builder.py).

```text
[prepare editable inputs]
├── [address only] search_addresses()    Photon suggestions; select the right match
└── [coordinates resolved]
    ├── AgentInput / AppointmentInput    validate input values
    ├── input_coordinates(agents, appointments)
    │   └── [all homes first, then appointments; pairs are (latitude, longitude)]
    ├── await get_travel_matrices(coordinates)
    │   ├── [at most 100 points] _request_table()
    │   └── [larger input] fill_block() → _request_table() for directed blocks
    └── build_problem(agents, appointments, distances, travel_times)
        ├── Agent(...) and Node(...)    assign consecutive IDs in matrix order
        └── ProblemData(...)
            └── __post_init__()
```

Address lookup happens before coordinates can be validated; `/api/solve` itself
receives coordinates, not address strings. The builder assigns home node IDs
equal to agent IDs. Saved datasets need not follow that home-ID convention.

## External services and ordering

[geocoding.py](../app/services/geocoding.py) queries public Photon and caches up
to 256 normalized query/limit pairs in memory. It returns labeled coordinates,
not a guaranteed unique address. `PHOTON_BASE_URL` and `PHOTON_USER_AGENT`
configure the provider. Resolve ambiguous matches before building a problem.

[osrm.py](../app/services/osrm.py) uses public OSRM's driving table endpoint.
It translates `(latitude, longitude)` into OSRM's longitude-first URL format.
Large tables use blocks of up to 50 origins/destinations with at most two
requests in flight. `_integer_matrix()` rounds provider costs to integers;
missing routes and unexpected matrix shapes raise errors, not zero-cost edges.
`OSRM_BASE_URL` selects another server. No live traffic is modeled.

Keep node order, coordinates, and matrix order aligned. A coordinate change
requires refreshed costs; reordering nodes requires matching matrix reindexing.
Schedule/gain changes alone do not require new routing requests.

The frontend's [load_sample()](../app/services/samples.py) returns editable
inputs without saved matrices, so an API solve requests fresh OSRM costs.
CLI solves use the saved matrices without network requests. Names and schedules
are not sent to Photon/OSRM; address queries or coordinates are.

For runnable manual-data preparation, see the
[manual-data guide](../.agents/skills/mtspa-routing/references/manual-data.md).
