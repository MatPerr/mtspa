# Metrics and incremental evaluation

[Documentation index](README.md)

Source: [metrics.py](../app/optimization/metrics.py).

`TourMetrics` describes one agent's route. `SolutionMetrics` combines all
routes. These values are independent of which loss config scores them.

## Call hierarchy

```text
solver.build_solution(tours, ...)
├── calculate_metrics(problem, tours, previous_metrics=None, changed_agent_ids=None)
│   ├── [no previous metrics]
│   │   └── calculate_tour_metrics(problem, agent_id, tour) for every route
│   ├── [previous metrics supplied]
│   │   ├── [copy the cached per-tour list]
│   │   └── calculate_tour_metrics(...) for changed_agent_ids only
│   └── calculate_solution_metrics(metrics_by_tour)
│       └── compute_std(total, sum_of_squares, count) for each standard deviation
├── calculate_loss(metrics, weights)
└── Solution(tours, tour_metrics, metrics, loss)
```

`previous_metrics` and `changed_agent_ids` must be supplied together. An empty
tuple means no routes changed: all route records are reused, but solution-wide
metrics are still aggregated. The helper does not mutate tours or the previous
metrics list. Callers must correctly identify every changed route.

## Simulating one route

The clock starts at the agent's workday start. For each successive node pair:

```text
arrival_time = current_time + travel_times[origin][destination]
├── [add this edge's distance and travel time]
├── [destination is home]
│   ├── overtime = max(0, arrival_time - workday_end)
│   └── current_time = arrival_time
└── [destination is an appointment]
    ├── time_difference = arrival_time - scheduled_time
    ├── waiting_time += max(0, -time_difference)
    ├── lateness += max(0, time_difference)
    └── current_time = max(arrival_time, scheduled_time) + service_duration
```

Late arrival delays departure and can propagate to later visits. Lateness is
summed per appointment; it is not just the last delay or an additional activity
duration. Waiting includes early arrival at the first appointment, but does
not include time at home after returning early.

Gain is summed over appointments. Elapsed time is return-home time minus
workday start, including travel, service, and waiting. Per-tour gain rates are:

```text
gain_per_km   = gain / (distance / 1000)
gain_per_hour = gain / (elapsed_time / 3600)
```

Rates are zero when their denominator is not positive. Travel time alone is
not the denominator of hourly gain. Distances remain metres in stored metrics.

## Aggregating the solution

`calculate_solution_metrics()` makes one pass over the per-tour records,
accumulating totals, sums, and squared sums. It does not replay routes.
`compute_std()` computes a population standard deviation:

```text
sqrt(max(0, sum_of_squares / count - (total / count) ** 2))
```

All agents, including unused agents, contribute to the standard deviations.
The `max(0, ...)` protects against tiny negative floating-point variance.
The seven std fields concern distance, travel time, gain, gain/km, gain/hour,
waiting time, and overtime. There is no lateness-std field.

`total_gain_per_km` and `total_gain_per_hour` are ratios of totals, not sums
or simple averages of individual rates. Total hourly gain uses the sum of
agents' elapsed times. Summed elapsed time is an intermediate, not an exported
`SolutionMetrics` field.

## Cost and cache scope

Full evaluation visits all route edges and aggregates all agents. After a
neighbor move, only the changed routes are simulated again; aggregation and
the shallow cache-list copy are still linear in the number of agents.

SA and calibration walks use this incremental path. DP scores its transitions
directly and calls the full metric evaluation only for final reconstructed
solutions. Cached route metrics are not DP's state table.
