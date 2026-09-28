# Loss calibration

[Documentation index](README.md)

Source: [loss_calibration.py](../app/optimization/loss_calibration.py).

Purpose: translate relative metric importances into weights for metrics measured
in different units. Calibration happens before optimization; weights stay fixed
throughout a run. It does not change the stored metric values.

## Function flow

```text
calibrate_loss_weights(problem, importances, scales=None)
├── [no scales supplied] estimate_metric_scales()
│   ├── random.Random(seed=0)            independent calibration RNG
│   ├── initialize_random_tours()
│   ├── calculate_metrics()              full initial evaluation
│   ├── [256 attempted moves by default]
│   │   ├── sample_neighbor()
│   │   ├── [no move] continue
│   │   ├── calculate_metrics(..., previous_metrics, changed_agent_ids)
│   │   ├── [collect each metric's absolute delta if greater than 1e-12]
│   │   └── [advance to the neighbor, including worse ones]
│   └── statistics.median(deltas) per metric; fallback 1.0 if none
└── [for each configured metric: importance × distance_scale / metric_scale]
    └── [return fixed weights]
```

The sampler follows an unconditional random walk, not an annealing run or a
walk restricted to feasible routes. It samples the current
[variation operators](variation_ops.md), so its scales describe typical changes
under those moves. Unavailable moves consume a sampling attempt.

## Distance scale versus metric scale

Both are computed by the same rule: the median nonzero absolute change of a
metric across sampled moves.

```text
distance_scale = scale for total_distance
metric_scale   = scale for the particular term being weighted
weight         = importance × distance_scale / metric_scale
```

Distance is the common reference unit, not a different statistic. For the
distance term itself, the scales cancel, so its weight equals its importance.

For example, suppose the sampled distance scale is 1,000 metres and the lateness
scale is 60 seconds. With lateness importance 11.7:

```text
distance weight = 1 × 1000 / 1000    = 1
lateness weight = 11.7 × 1000 / 60  = 195
one typical lateness change costs 60 × 195 = 11,700 loss units
```

This makes that typical lateness change cost 11.7 times a typical distance
change. It is not a promise about exact trade-offs for every possible move.

## Several configs and parallel runs

```text
calibrate_loss_weights_for_configs(problem, configs)
├── [collect the union of required metrics, always including total_distance]
├── estimate_metric_scales()             one walk shared by all configs
└── [for each config]
    └── calibrate_loss_weights(..., scales=shared_scales)
```

Full SA passes those calibrated weights to every worker; workers do not repeat
this walk. Lite SA likewise shares its parent's weights across parallel runs.
Full DP calibrates its one/two configs together. Lite DP calibrates its single
config unless weights were supplied explicitly.

Loss calibration's fixed local seed does not advance the solver's RNG. This is
different from [temperature calibration](temperature_calibration.md), which
uses the solver's RNG and its actual starting solution.

## Limits

The sample count is bounded and the walk need not resemble final good routes.
If no change is observed, the fallback scale `1.0` is a practical default, not
an estimate of a hidden distribution. Normalization improves portability across
datasets but does not guarantee feasibility, identical behavior under all data
changes, or a specific fairness outcome. Changing the move operators can change
the calibrated weights.
