import json
from pathlib import Path

from app.optimization.datamodel import Agent, Matrix, Node


def load_data(
    filepath: str | Path,
) -> tuple[list[Node], list[Agent], Matrix[int], Matrix[int]]:
    with Path(filepath).open(encoding="utf-8") as file:
        data = json.load(file)

    nodes = [
        Node(
            id=int(item["id"]),
            latitude=float(item["lat"]),
            longitude=float(item["lng"]),
            time=int(item["time"]),
            duration=int(item["duration"]),
            kind=str(item["type"]),
            agent_id=(
                None
                if item["agent_id"] is None
                else int(item["agent_id"])
            ),
            gain=int(item["gain"]),
        )
        for item in sorted(data["nodes"], key=lambda item: int(item["id"]))
    ]
    agents = [
        Agent(
            id=int(item["id"]),
            name=str(item["name"]),
            start_time=int(item["startTime"]),
            end_time=int(item["endTime"]),
        )
        for item in sorted(data["agents"], key=lambda item: int(item["id"]))
    ]
    distances = [list(map(int, row)) for row in data["D"]]
    travel_times = [list(map(int, row)) for row in data["T"]]

    return nodes, agents, distances, travel_times
