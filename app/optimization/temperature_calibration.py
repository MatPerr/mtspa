import math
import random
import statistics
from dataclasses import dataclass

from app.optimization.datamodel import ProblemData, Solution
from app.optimization.metrics import evaluate_neighbor_metrics
from app.optimization.objectives import ResolvedLossConfig, calculate_loss
from app.optimization.variation_ops import sample_neighbor

INITIAL_ACCEPTANCE_PROBABILITY = 0.8
FINAL_ACCEPTANCE_PROBABILITY = 0.001


@dataclass(frozen=True, slots=True)
class TemperatureCalibration:
    initial_temperature: float
    final_temperature: float
    cooling_rate: float


def estimate_typical_delta(
    problem: ProblemData,
    rng: random.Random,
    solution: Solution,
    loss_config: ResolvedLossConfig,
    samples: int,
) -> float:
    delta_magnitudes = []

    for _ in range(samples):
        neighbor = sample_neighbor(problem, rng, solution.tours)
        if neighbor is None:
            continue

        neighbor_tours, changed_agent_ids = neighbor
        _, metrics = evaluate_neighbor_metrics(
            problem,
            neighbor_tours,
            previous_metrics=solution.tour_metrics,
            changed_agent_ids=changed_agent_ids,
        )
        delta = calculate_loss(metrics, loss_config) - solution.loss
        if delta != 0:
            delta_magnitudes.append(abs(delta))

    return statistics.median(delta_magnitudes)


def calibrate_temperature(
    problem: ProblemData,
    rng: random.Random,
    solution: Solution,
    loss_config: ResolvedLossConfig,
    steps: int,
) -> TemperatureCalibration:
    samples = min(100, max(1, steps // 10))
    typical_delta = estimate_typical_delta(
        problem,
        rng,
        solution,
        loss_config,
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
