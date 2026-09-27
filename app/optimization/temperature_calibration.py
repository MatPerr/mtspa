import math
import random
import statistics
from dataclasses import dataclass

from app.optimization.datamodel import ProblemData, Solution
from app.optimization.metrics import calculate_metrics
from app.optimization.objectives import MetricName, calculate_loss
from app.optimization.variation_ops import sample_neighbor

INITIAL_ACCEPTANCE_PROBABILITY = 0.8
FINAL_ACCEPTANCE_PROBABILITY = 1e-12


@dataclass(frozen=True, slots=True)
class TemperatureCalibration:
    initial_temperature: float
    final_temperature: float
    cooling_rate: float


def estimate_typical_delta(
    problem: ProblemData,
    rng: random.Random,
    solution: Solution,
    weights: dict[MetricName, float],
    samples: int,
) -> float:
    """Estimate a typical loss change around one fixed solution.

    Every neighbor is sampled from solution, without advancing a random walk.
    Improvements and worsenings both contribute their absolute loss changes;
    equal-cost moves are excluded. Sampling advances rng but preserves solution.

    Args:
        problem: Routing problem used to evaluate neighbors.
        rng: Random generator used to propose moves.
        solution: Fixed starting solution with valid cached metrics and loss.
        weights: Calibrated weights used to compute solution.loss.
        samples: Number of move attempts.

    Returns:
        Median nonzero absolute loss change, or 1.0 when no such change is found.
    """
    delta_magnitudes = []

    for _ in range(samples):
        neighbor = sample_neighbor(problem, rng, solution.tours)
        if neighbor is None:
            continue

        neighbor_tours, changed_agent_ids = neighbor
        _, metrics = calculate_metrics(
            problem,
            neighbor_tours,
            previous_metrics=solution.tour_metrics,
            changed_agent_ids=changed_agent_ids,
        )
        delta = calculate_loss(metrics, weights) - solution.loss
        if delta != 0:
            delta_magnitudes.append(abs(delta))

    # Equal-cost swaps (or no available moves) can leave the sample empty.
    return statistics.median(delta_magnitudes) if delta_magnitudes else 1.0


def calibrate_temperature(
    problem: ProblemData,
    rng: random.Random,
    solution: Solution,
    weights: dict[MetricName, float],
    steps: int,
) -> TemperatureCalibration:
    """Choose endpoint temperatures and a geometric cooling multiplier.

    Use up to 100 move attempts around solution to estimate a typical delta.
    Each endpoint uses T = -delta / log(p), so a worsening move of that size
    has the configured acceptance probability. Both endpoints use the same
    initial estimate; the schedule does not adapt to later neighborhoods.

    Args:
        problem: Routing problem to sample.
        rng: Random generator, advanced by calibration sampling.
        solution: Initial solution with metrics and loss already evaluated.
        weights: Calibrated weights used for solution and its neighbors.
        steps: Planned positive number of annealing steps.

    Returns:
        Initial and final temperatures and the per-step multiplier. With more
        than one step, the last iteration uses the final temperature.
    """
    samples = min(100, max(1, steps // 10))
    typical_delta = estimate_typical_delta(
        problem,
        rng,
        solution,
        weights,
        samples,
    )
    initial_temperature = (
        -typical_delta / math.log(INITIAL_ACCEPTANCE_PROBABILITY)
    )
    final_temperature = (
        -typical_delta / math.log(FINAL_ACCEPTANCE_PROBABILITY)
    )
    cooling_rate = (
        final_temperature / initial_temperature
    ) ** (1 / max(steps - 1, 1))

    return TemperatureCalibration(
        initial_temperature=initial_temperature,
        final_temperature=final_temperature,
        cooling_rate=cooling_rate,
    )
