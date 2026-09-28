# Objectives and loss configs

[Documentation index](README.md)

Source: [objectives.py](../app/optimization/objectives.py).

Metrics describe a solution. The loss decides which solution is preferred.
Both solvers minimize loss; a smaller value is better for that fixed objective.

```text
LOSS_CONFIGS[config_id] → LossConfig
├── id, name, description
├── supported_solvers
└── importances: dict[MetricName, float]
    └── calibrate_loss_weights(problem, importances)
        └── weights: dict[MetricName, float]
            └── calculate_loss(solution.metrics, weights)
                └── sum(weight × corresponding metric)
```

`MetricName` is a string enum matching `SolutionMetrics` field names.
`calculate_loss()` uses those names with `getattr()`; it neither simulates
routes nor calibrates weights. `get_loss_configs()` resolves IDs into config
objects; caller validation handles duplicate or incompatible choices.

## Built-in configs

These are **importances**, not the final raw-unit weights. All four configs
include distance importance `1` and lateness importance `11.7`.

| Config ID | Additional term and importance | Solvers |
| --- | --- | --- |
| `shortest_distance` | None | SA, DP |
| `fair_hourly_pay` | `gain_per_hour_std`: `0.1624` | SA |
| `fair_distance` | `distance_std`: `1.262` | SA |
| `maximum_uptime` | `total_waiting_time`: `0.5343` | SA, DP |

The default is `shortest_distance`. Built-in distance weight remains `1`
after [loss calibration](loss_calibration.md); other weights depend on the
dataset's sampled metric changes.

## Preferences versus constraints

SA uses the weighted sum as a soft preference. A high lateness penalty does
not guarantee zero lateness. The current built-in configs do not include an
overtime penalty, although overtime is measured and reported.
Fairness is also a trade-off: a fairness config does not impose equal routes
or guarantee a lower standard deviation in every approximate run.

DP enforces on-time appointments and return home as hard constraints. Lateness
and overtime are therefore zero in its returned solutions. Its recurrence
supports additive distance and waiting costs. Global standard deviations are
not represented in that state/cost recurrence, so the fairness configs are
rejected rather than silently approximated.

Changing the metadata of a config to say it supports DP does not extend the
DP recurrence. A new DP objective requires verifying that the state retains
all information needed to compare future continuations correctly.

Compare raw losses only under the same weights and problem. Different configs
or independently calibrated datasets may have different scales.
