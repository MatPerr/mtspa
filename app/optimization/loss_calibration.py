import random
import statistics
from collections.abc import Iterable

from app.optimization.datamodel import ProblemData
from app.optimization.metrics import (
    calculate_solution_metrics,
    calculate_tour_metrics,
    evaluate_neighbor_metrics,
)
from app.optimization.objectives import LossConfig, MetricName
from app.optimization.variation_ops import (
    initialize_random_tours,
    sample_neighbor,
)

DEFAULT_CALIBRATION_SAMPLES = 256
DEFAULT_CALIBRATION_SEED = 0


def estimate_metric_scales(
    problem: ProblemData,
    metrics: Iterable[MetricName],
    *,
    samples: int = DEFAULT_CALIBRATION_SAMPLES,
    seed: int = DEFAULT_CALIBRATION_SEED,
) -> dict[MetricName, float]:
    """Estimate typical per-metric changes using an unconditional random walk.

    Start from a random assignment and advance to every sampled neighbor,
    including worse ones. For each metric, collect absolute changes greater
    than 1e-12. These scales describe sampled moves, not the metric totals.

    Args:
        problem: Routing problem to sample.
        metrics: Metric names to measure; duplicates are removed.
        samples: Positive number of move attempts, including unavailable moves.
        seed: Seed for a local random generator independent of the solver's RNG.

    Returns:
        Median change magnitude for each metric, or 1.0 if no nonzero changes
        were observed for that metric.

    Raises:
        ValueError: samples is not positive.
    """
    if samples <= 0:
        raise ValueError("samples must be positive")

    selected_metrics = tuple(dict.fromkeys(metrics))
    deltas = {metric: [] for metric in selected_metrics}
    rng = random.Random(seed)
    tours = initialize_random_tours(problem, rng)
    metrics_by_tour = [
        calculate_tour_metrics(problem, agent_id, tour)
        for agent_id, tour in enumerate(tours)
    ]
    solution_metrics = calculate_solution_metrics(metrics_by_tour)

    for _ in range(samples):
        neighbor = sample_neighbor(problem, rng, tours)
        if neighbor is None:
            continue

        neighbor_tours, changed_agent_ids = neighbor
        neighbor_metrics_by_tour, neighbor_metrics = evaluate_neighbor_metrics(
            problem,
            neighbor_tours,
            previous_metrics=metrics_by_tour,
            changed_agent_ids=changed_agent_ids,
        )

        for metric in selected_metrics:
            delta = abs(
                getattr(neighbor_metrics, metric.value)
                - getattr(solution_metrics, metric.value)
            )
            if delta > 1e-12:
                deltas[metric].append(delta)

        tours = neighbor_tours
        metrics_by_tour = neighbor_metrics_by_tour
        solution_metrics = neighbor_metrics

    return {
        metric: (
            statistics.median(metric_deltas)
            if metric_deltas
            else 1.0
        )
        for metric, metric_deltas in deltas.items()
    }


def calibrate_loss_weights(
    problem: ProblemData,
    importances: dict[MetricName, float],
    *,
    scales: dict[MetricName, float] | None = None,
) -> dict[MetricName, float]:
    """Convert relative metric importances into fixed scoring weights.

    Each weight is importance * distance_scale / metric_scale, making typical
    changes comparable to distance. Neither importances nor scales is mutated.

    Args:
        problem: Routing problem used when metric scales need to be estimated.
        importances: Chosen relative priorities keyed by metric name.
        scales: Optional positive metric scales from a shared calibration walk.
            Must include distance and every metric in importances. When omitted,
            estimate them from problem.

    Returns:
        A new dictionary of numeric weights for use throughout optimization.
    """
    if scales is None:
        metric_names = set(importances)
        metric_names.add(MetricName.TOTAL_DISTANCE)
        scales = estimate_metric_scales(problem, metric_names)
    distance_scale = scales[MetricName.TOTAL_DISTANCE]

    weights = {}
    for metric, importance in importances.items():
        weights[metric] = importance * distance_scale / scales[metric]
    return weights


def calibrate_loss_weights_for_configs(
    problem: ProblemData,
    configs: Iterable[LossConfig],
) -> tuple[dict[MetricName, float], ...]:
    """Calibrate several objectives using a single shared sampling walk.

    Args:
        problem: Routing problem used to estimate metric scales.
        configs: Objective definitions whose importance dictionaries are preserved.

    Returns:
        One weight dictionary per configuration, in input order. Empty input
        produces an empty tuple without sampling.
    """
    configs = tuple(configs)
    if not configs:
        return ()

    metric_names = {MetricName.TOTAL_DISTANCE}
    for config in configs:
        metric_names.update(config.importances)
    scales = estimate_metric_scales(problem, metric_names)

    return tuple(
        calibrate_loss_weights(problem, config.importances, scales=scales)
        for config in configs
    )
