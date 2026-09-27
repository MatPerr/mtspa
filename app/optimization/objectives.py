from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.optimization.datamodel import SolutionMetrics


type LossConfigId = Literal[
    "shortest_distance",
    "fair_hourly_pay",
    "fair_distance",
    "maximum_uptime",
]
type SolverName = Literal["sa", "dp"]


class MetricName(StrEnum):
    TOTAL_DISTANCE = "total_distance"
    DISTANCE_STD = "distance_std"
    TOTAL_TRAVEL_TIME = "total_travel_time"
    TRAVEL_TIME_STD = "travel_time_std"
    TOTAL_GAIN = "total_gain"
    GAIN_STD = "gain_std"
    TOTAL_GAIN_PER_KM = "total_gain_per_km"
    GAIN_PER_KM_STD = "gain_per_km_std"
    TOTAL_GAIN_PER_HOUR = "total_gain_per_hour"
    GAIN_PER_HOUR_STD = "gain_per_hour_std"
    TOTAL_LATENESS = "total_lateness"
    TOTAL_WAITING_TIME = "total_waiting_time"
    WAITING_TIME_STD = "waiting_time_std"
    TOTAL_OVERTIME = "total_overtime"
    OVERTIME_STD = "overtime_std"


@dataclass(frozen=True, slots=True)
class LossConfig:
    id: LossConfigId
    name: str
    description: str
    supported_solvers: tuple[SolverName, ...]
    importances: dict[MetricName, float]


def calculate_loss(
    metrics: SolutionMetrics,
    weights: dict[MetricName, float],
) -> float:
    return sum(
        weight * getattr(metrics, metric.value)
        for metric, weight in weights.items()
    )


LOSS_CONFIGS: dict[LossConfigId, LossConfig] = {
    "shortest_distance": LossConfig(
        id="shortest_distance",
        name="Shortest distance",
        description="Prioritize total distance while strongly penalizing lateness.",
        supported_solvers=("sa", "dp"),
        importances={
            MetricName.TOTAL_DISTANCE: 1,
            MetricName.TOTAL_LATENESS: 11.7,
        },
    ),
    "fair_hourly_pay": LossConfig(
        id="fair_hourly_pay",
        name="Fair hourly pay",
        description="Reduce differences in gain per hour between agents.",
        supported_solvers=("sa",),
        importances={
            MetricName.TOTAL_DISTANCE: 1,
            MetricName.TOTAL_LATENESS: 11.7,
            MetricName.GAIN_PER_HOUR_STD: 0.1624,
        },
    ),
    "fair_distance": LossConfig(
        id="fair_distance",
        name="Fair distance",
        description="Distribute travelled distance more evenly between agents.",
        supported_solvers=("sa",),
        importances={
            MetricName.TOTAL_DISTANCE: 1,
            MetricName.TOTAL_LATENESS: 11.7,
            MetricName.DISTANCE_STD: 1.262,
        },
    ),
    "maximum_uptime": LossConfig(
        id="maximum_uptime",
        name="Maximum uptime",
        description="Reduce total waiting time between appointments.",
        supported_solvers=("sa", "dp"),
        importances={
            MetricName.TOTAL_DISTANCE: 1,
            MetricName.TOTAL_LATENESS: 11.7,
            MetricName.TOTAL_WAITING_TIME: 0.5343,
        },
    ),
}

DEFAULT_LOSS_CONFIG = LOSS_CONFIGS["shortest_distance"]


def get_loss_configs(config_ids: list[LossConfigId]) -> list[LossConfig]:
    return [LOSS_CONFIGS[config_id] for config_id in config_ids]
