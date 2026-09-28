# Data model

[Documentation index](README.md)

Sources: [datamodel.py](../app/optimization/datamodel.py),
[results.py](../app/optimization/results.py).

## Ownership and indexing

```text
ProblemData                              shared input for a solve
├── nodes: list[Node]                    indexed by node ID
│   └── id, latitude, longitude, time, duration, kind, agent_id, gain
├── agents: list[Agent]                  indexed by agent ID
│   └── id, name, start_time, end_time
├── distances: list[list[int]]           metres, [origin node][destination node]
├── travel_times: list[list[int]]        seconds, same indexing
└── derived lists and feasibility tables

Solution                                one evaluated assignment
├── tours: list[list[NodeId]]            outer index = agent ID
├── tour_metrics: list[TourMetrics]      same outer indexing
├── metrics: SolutionMetrics            totals and cross-agent statistics
└── loss: float                         weighted objective score

ConfigOptimizationResult                full solvers / app wrapper
├── config: LossConfig
├── solution: Solution
└── annealing_history: AnnealingHistory | None
    ├── run_number, run_count
    └── points: list[AnnealingHistoryPoint]
        └── iteration, current_loss, best_loss
```

`AgentId` and `NodeId` are aliases of `int`, not runtime-distinct classes.
`Tour` is `list[NodeId]`, `Tours` is `list[Tour]`, and `Matrix[T]` is
`list[list[T]]`. No Pandas or NumPy structure is needed here.

A route includes its home at both ends: `[home, appointment, ..., home]`.
An unused agent has `[home, home]`. Home node IDs do not necessarily equal
agent IDs: use `problem.agent_home_nodes[agent_id]`. Coordinates live only
on nodes; an agent's home node connects its identity to its location.
The appointment assignment is represented by `Solution.tours`, not by changing
appointment nodes' `agent_id` fields.

## Validation and precomputation

```text
ProblemData.__post_init__()
├── [require nodes and agents to be indexed consecutively from zero]
├── [require both matrices to be N × N]
├── [build node_times, node_durations, node_gains, node_is_home, appointment_ids]
├── [build agent_start_times, agent_end_times, agent_home_nodes]
├── [require exactly one home with a valid owner per agent]
├── [derive on-time departure at each node]
├── [build can_follow[origin][destination]]
└── [build can_return_home[agent][node]]
```

At a home, departure is the owner's workday start. At an appointment, the
precomputed departure is scheduled time plus duration.
`can_follow` requires an appointment destination and on-time arrival.
`can_return_home` checks departure plus the trip home against workday end;
already being at the agent's home is allowed.

These tables are suitable for DP, whose paths stay on time. SA can arrive late,
so [metrics](metrics.md) simulates actual evolving arrival/departure times.

Validation here is structural, not exhaustive: it does not enforce coordinate
bounds, nonnegative matrix entries, or all workday rules. The API applies
additional checks through [schemas.py](../app/schemas.py). Direct dataclass
construction does not validate a tour's coverage or ensure its cached metrics
agree with its routes.

## Mutability and cached values

`Node`, `Agent`, `TourMetrics`, and `SolutionMetrics` use `frozen=True` and
`slots=True`. `ProblemData` and `Solution` use slots but are not frozen.
Slots prevent arbitrary extra instance attributes; they do not freeze lists.

Treat a constructed problem as fixed: editing its lists does not rebuild its
precomputed fields automatically. Likewise, do not mutate a solution's tours
after scoring it: its metrics and loss would become stale.
[sample_neighbor()](variation_ops.md) copies the outer tours list and the two
changed routes, allowing previous solutions and unaffected metrics to be reused.

Distances use metres; travel, duration, waiting, lateness, and overtime use
seconds. Scheduled/workday times are seconds from midnight. Gain is an
application-defined integer unit; keep that unit consistent throughout a dataset.
