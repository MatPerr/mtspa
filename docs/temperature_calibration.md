# Temperature calibration

[Documentation index](README.md)

Source: [temperature_calibration.py](../app/optimization/temperature_calibration.py).

SA accepts worsening moves with probability `exp(-loss_change / temperature)`.
Temperature calibration picks a useful starting scale and a geometric cooling
schedule in the units of the already-calibrated loss. DP does not use it.

## Function flow

```text
solver.optimize(steps)
├── initialize_solution() → current
└── calibrate_temperature(problem, rng, current, weights, steps)
    ├── [samples = min(100, max(1, steps // 10))]
    ├── estimate_typical_delta(..., samples)
    │   ├── [repeat up to samples attempts, always from current.tours]
    │   │   ├── sample_neighbor()
    │   │   ├── [no move] continue
    │   │   ├── calculate_metrics(..., cached current metrics, changed IDs)
    │   │   ├── calculate_loss(neighbor_metrics, weights)
    │   │   └── [collect abs(neighbor_loss - current.loss) if nonzero]
    │   └── statistics.median(deltas), or 1.0 if no nonzero delta exists
    ├── [derive initial/final temperatures from acceptance probabilities]
    ├── [derive cooling_rate once]
    └── TemperatureCalibration(initial_temperature, final_temperature, cooling_rate)
```

Unlike loss calibration, this samples around **one fixed starting solution**;
it does not advance a random walk. Improving and worsening deltas both
contribute their absolute magnitudes. Neither the solution nor its tours is
modified, but sampling does advance the solver's RNG.

## Temperature formulas

Let `delta` be the typical nonzero loss change. Solve
`p = exp(-delta / temperature)` for temperature:

```text
initial_temperature = -delta / log(0.8)
final_temperature   = -delta / log(1e-12)
cooling_rate        = (final_temperature / initial_temperature)
                     ** (1 / max(steps - 1, 1))
```

At the start, a worsening move of size `delta` has an 80% acceptance probability;
at the end, its target probability is `1e-12`. Other move sizes have different
probabilities. The constants live in the calibration module.

The optimizer starts at `initial_temperature` and multiplies by `cooling_rate`
after every attempted step, including attempts with no available neighbor.
With more than one step, the last step uses approximately `final_temperature`
(up to floating-point rounding). With one step, only the initial temperature
is used. The expensive power is evaluated once, not each iteration.

## Relationship to loss calibration

| Calibration | Chooses | Samples from | RNG |
| --- | --- | --- | --- |
| [Loss calibration](loss_calibration.md) | Fixed weights for individual metrics | A random walk | Separate fixed seed |
| Temperature calibration | Temperature endpoints and cooling rate | The run's fixed initial solution | The run's RNG |

Each parallel SA run calibrates its own temperature after creating its own
initial solution, while reusing the parent's loss weights. The fallback `1.0`
keeps temperatures positive when moves are unavailable or all sampled losses
are equal; it is not derived from the absolute current loss.

Reproducibility depends on the initial seed, problem, weights, and step budget:
changing the step budget can change both the calibration sample count and the
subsequent RNG state.
