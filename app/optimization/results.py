from dataclasses import dataclass

from app.optimization.datamodel import Solution
from app.optimization.objectives import LossConfig


@dataclass(frozen=True, slots=True)
class AnnealingHistoryPoint:
    iteration: int
    current_loss: float
    best_loss: float


@dataclass(frozen=True, slots=True)
class AnnealingHistory:
    run_number: int
    run_count: int
    points: list[AnnealingHistoryPoint]


@dataclass(frozen=True, slots=True)
class ConfigOptimizationResult:
    config: LossConfig
    solution: Solution
    annealing_history: AnnealingHistory | None = None
