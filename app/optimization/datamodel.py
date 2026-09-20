from dataclasses import dataclass, field


type AgentId = int
type NodeId = int
type Tour = list[NodeId]
type Tours = list[Tour]
type Matrix[T] = list[list[T]]


@dataclass(frozen=True, slots=True)
class Node:
    id: NodeId
    latitude: float
    longitude: float
    time: int
    duration: int
    kind: str
    agent_id: AgentId | None
    gain: int


@dataclass(frozen=True, slots=True)
class Agent:
    id: AgentId
    name: str
    start_time: int
    end_time: int


@dataclass(slots=True)
class ProblemData:
    nodes: list[Node]
    agents: list[Agent]
    distances: Matrix[int]
    travel_times: Matrix[int]
    node_times: list[int] = field(init=False, repr=False)
    node_durations: list[int] = field(init=False, repr=False)
    node_gains: list[int] = field(init=False, repr=False)
    node_is_home: list[bool] = field(init=False, repr=False)
    appointment_ids: list[NodeId] = field(init=False, repr=False)
    agent_start_times: list[int] = field(init=False, repr=False)
    agent_end_times: list[int] = field(init=False, repr=False)
    agent_home_nodes: list[NodeId] = field(init=False, repr=False)
    can_follow: Matrix[bool] = field(init=False, repr=False)
    can_return_home: Matrix[bool] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        node_count = len(self.nodes)
        agent_count = len(self.agents)
        node_ids = [node.id for node in self.nodes]
        agent_ids = [agent.id for agent in self.agents]

        if node_ids != list(range(node_count)):
            raise ValueError("Node IDs must be consecutive and start at 0")
        if agent_ids != list(range(agent_count)):
            raise ValueError("Agent IDs must be consecutive and start at 0")
        if len(self.distances) != node_count or any(
            len(row) != node_count for row in self.distances
        ):
            raise ValueError("Distance matrix shape does not match the nodes")
        if len(self.travel_times) != node_count or any(
            len(row) != node_count for row in self.travel_times
        ):
            raise ValueError("Travel-time matrix shape does not match the nodes")

        self.node_times = [node.time for node in self.nodes]
        self.node_durations = [node.duration for node in self.nodes]
        self.node_gains = [node.gain for node in self.nodes]
        self.node_is_home = [node.kind == "home" for node in self.nodes]
        self.appointment_ids = [
            node.id for node in self.nodes if node.kind != "home"
        ]
        self.agent_start_times = [agent.start_time for agent in self.agents]
        self.agent_end_times = [agent.end_time for agent in self.agents]
        self.agent_home_nodes = [-1] * agent_count

        for node in self.nodes:
            if node.kind != "home":
                continue
            if node.agent_id is None or not 0 <= node.agent_id < agent_count:
                raise ValueError(f"Home node {node.id} has an invalid agent_id")
            if self.agent_home_nodes[node.agent_id] != -1:
                raise ValueError(f"Agent {node.agent_id} has multiple home nodes")
            self.agent_home_nodes[node.agent_id] = node.id

        if any(home_node < 0 for home_node in self.agent_home_nodes):
            raise ValueError("Each agent must have exactly one home node")

        departure_times = [
            time + duration
            for time, duration in zip(
                self.node_times,
                self.node_durations,
                strict=True,
            )
        ]
        for agent_id, home_node in enumerate(self.agent_home_nodes):
            departure_times[home_node] = self.agent_start_times[agent_id]

        self.can_follow = [
            [
                not self.node_is_home[destination]
                and departure_times[origin]
                + self.travel_times[origin][destination]
                <= self.node_times[destination]
                for destination in range(node_count)
            ]
            for origin in range(node_count)
        ]
        self.can_return_home = []
        for agent_id, home_node in enumerate(self.agent_home_nodes):
            self.can_return_home.append(
                [
                    node_id == home_node
                    or self.node_times[node_id]
                    + self.node_durations[node_id]
                    + self.travel_times[node_id][home_node]
                    <= self.agent_end_times[agent_id]
                    for node_id in range(node_count)
                ]
            )


@dataclass(frozen=True, slots=True)
class TourMetrics:
    distance: int
    travel_time: int
    gain: int
    elapsed_time: int
    gain_per_km: float
    gain_per_hour: float
    lateness: int
    waiting_time: int
    overtime: int


@dataclass(frozen=True, slots=True)
class SolutionMetrics:
    total_distance: int
    distance_std: float
    total_travel_time: int
    travel_time_std: float
    total_gain: int
    gain_std: float
    total_gain_per_km: float
    gain_per_km_std: float
    total_gain_per_hour: float
    gain_per_hour_std: float
    total_lateness: int
    total_waiting_time: int
    waiting_time_std: float
    total_overtime: int
    overtime_std: float


@dataclass(slots=True)
class Solution:
    tours: Tours
    tour_metrics: list[TourMetrics]
    metrics: SolutionMetrics
    loss: float
