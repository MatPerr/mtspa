import random
import statistics
from collections.abc import Iterable
from typing import cast

from app.optimization.datamodel import ProblemData
from app.optimization.metrics import (
    calculate_solution_metrics,
    calculate_tour_metrics,
)
from app.optimization.objectives import (
    AnyLossConfig,
    LossConfig,
    MetricName,
    ResolvedLossConfig,
    ResolvedLossTerm,
)
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
        neighbor_metrics_by_tour = metrics_by_tour.copy()
        for agent_id in changed_agent_ids:
            neighbor_metrics_by_tour[agent_id] = calculate_tour_metrics(
                problem,
                agent_id,
                neighbor_tours[agent_id],
            )
        neighbor_metrics = calculate_solution_metrics(
            neighbor_metrics_by_tour
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


def resolve_loss_configs(
    problem: ProblemData,
    configs: Iterable[AnyLossConfig],
) -> tuple[ResolvedLossConfig, ...]:
    selected_configs = tuple(configs)
    unresolved_configs = tuple(
        config
        for config in selected_configs
        if isinstance(config, LossConfig)
    )
    if not unresolved_configs:
        return cast(tuple[ResolvedLossConfig, ...], selected_configs)

    metric_names = {
        MetricName.TOTAL_DISTANCE,
        *(
            term.metric
            for config in unresolved_configs
            for term in config.terms
        ),
    }
    scales = estimate_metric_scales(problem, metric_names)
    distance_scale = scales[MetricName.TOTAL_DISTANCE]

    return tuple(
        config
        if isinstance(config, ResolvedLossConfig)
        else ResolvedLossConfig(
            id=config.id,
            name=config.name,
            description=config.description,
            supported_solvers=config.supported_solvers,
            terms=tuple(
                ResolvedLossTerm(
                    metric=term.metric,
                    weight=(
                        term.importance
                        * distance_scale
                        / scales[term.metric]
                    ),
                )
                for term in config.terms
            ),
        )
        for config in selected_configs
    )


def resolve_loss_config(
    problem: ProblemData,
    config: AnyLossConfig,
) -> ResolvedLossConfig:
    return resolve_loss_configs(problem, (config,))[0]
