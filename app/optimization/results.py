from dataclasses import dataclass

from app.optimization.datamodel import Solution
from app.optimization.objectives import ResolvedLossConfig


@dataclass(frozen=True, slots=True)
class ConfigOptimizationResult:
    config: ResolvedLossConfig
    solution: Solution
