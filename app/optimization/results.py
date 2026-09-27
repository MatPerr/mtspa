from dataclasses import dataclass

from app.optimization.datamodel import Solution
from app.optimization.objectives import LossConfig


@dataclass(frozen=True, slots=True)
class ConfigOptimizationResult:
    config: LossConfig
    solution: Solution
