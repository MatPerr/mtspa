from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.optimization.objectives import LOSS_CONFIGS, LossConfigId


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GeocodeSuggestion(Coordinate):
    label: str


class AgentInput(Coordinate):
    name: str = Field(min_length=1, max_length=100)
    start_time: int = Field(ge=0, lt=86_400)
    end_time: int = Field(gt=0, le=86_400)

    @model_validator(mode="after")
    def validate_workday(self) -> Self:
        """Require a workday that ends strictly after it starts.

        Returns:
            This validated agent input.

        Raises:
            ValueError: end_time is not later than start_time.
        """
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AppointmentInput(Coordinate):
    time: int = Field(ge=0, lt=86_400)
    duration: int = Field(ge=0)
    gain: int = Field(ge=0)


class SampleProblemResponse(BaseModel):
    agents: list[AgentInput]
    appointments: list[AppointmentInput]


class SampleDatasetResponse(BaseModel):
    id: str
    name: str
    description: str
    agent_count: int
    appointment_count: int


class LossTermResponse(BaseModel):
    metric: str
    importance: float


class LossConfigResponse(BaseModel):
    id: LossConfigId
    name: str
    description: str
    supported_solvers: list[Literal["sa", "dp"]]
    terms: list[LossTermResponse]


class SolveRequest(BaseModel):
    solver: Literal["sa", "dp"] = "sa"
    agents: list[AgentInput] = Field(min_length=1)
    appointments: list[AppointmentInput] = Field(min_length=1)
    steps: int = Field(default=50_000, ge=1)
    runs: int = Field(default=1, ge=1)
    seed: int | None = None
    max_states: int = Field(default=8_000_000, ge=1)
    loss_config_ids: list[LossConfigId] = Field(
        default_factory=lambda: ["shortest_distance"],
        min_length=1,
        max_length=4,
    )

    @model_validator(mode="after")
    def validate_solver_options(self) -> Self:
        """Check agent counts and objective compatibility for the chosen solver.

        Returns:
            This request after checking the constraints spanning multiple fields.

        Raises:
            ValueError: SA has fewer than two agents, objective IDs repeat,
                DP has more than two objectives, or an objective does not
                support the selected solver.
        """
        if self.solver == "sa" and len(self.agents) < 2:
            raise ValueError("Simulated annealing requires at least two agents")
        if len(self.loss_config_ids) != len(set(self.loss_config_ids)):
            raise ValueError("loss_config_ids must not contain duplicates")
        if self.solver == "dp" and len(self.loss_config_ids) > 2:
            raise ValueError("Dynamic programming accepts at most two configs")
        unsupported_configs = [
            config_id
            for config_id in self.loss_config_ids
            if self.solver not in LOSS_CONFIGS[config_id].supported_solvers
        ]
        if unsupported_configs:
            raise ValueError(
                f"Loss configs not supported by {self.solver}: "
                + ", ".join(unsupported_configs)
            )
        return self


class TimelineSegmentResponse(BaseModel):
    kind: Literal["travel", "waiting", "appointment", "lateness", "overtime", "available"]
    start_time: int
    end_time: int
    appointment_id: int | None = None


class TourTimelineResponse(BaseModel):
    end_time: int
    workday_start: int
    workday_end: int
    return_time: int
    segments: list[TimelineSegmentResponse]


class TourResponse(BaseModel):
    agent_id: int
    agent_name: str
    node_ids: list[int]
    appointment_ids: list[int]
    coordinates: list[Coordinate]
    metrics: dict[str, int | float]
    timeline: TourTimelineResponse


class AnnealingHistoryPointResponse(BaseModel):
    iteration: int
    current_loss: float
    best_loss: float


class AnnealingHistoryResponse(BaseModel):
    run_number: int
    run_count: int
    points: list[AnnealingHistoryPointResponse]


class ConfigSolutionResponse(BaseModel):
    loss_config_id: LossConfigId
    loss_config_name: str
    loss: float
    metrics: dict[str, int | float]
    tours: list[TourResponse]
    final_state_count: int | None = None
    annealing_history: AnnealingHistoryResponse | None = None


class SolveResponse(BaseModel):
    solver: Literal["sa", "dp"]
    elapsed_seconds: float
    solutions: list[ConfigSolutionResponse]
