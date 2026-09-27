import html
import json
import math
from pathlib import Path

from app.optimization.datamodel import ProblemData, Solution, Tour, TourMetrics


def save_solution_report(
    problem: ProblemData,
    solution: Solution,
    final_state_count: int,
    elapsed_seconds: float,
    output_directory: str | Path = "artifacts",
) -> tuple[Path, Path]:
    """Write a distance summary and standalone SVG visualization to disk.

    Create the destination directory if needed and overwrite the two fixed
    report filenames when they already exist.

    Args:
        problem: Routing data used for names, coordinates, and appointment times.
        solution: Evaluated solution to report.
        final_state_count: Number of states in the final DP layer.
        elapsed_seconds: Solver runtime to display in seconds.
        output_directory: Directory receiving the JSON and SVG files.

    Returns:
        Paths to optimal_distance_summary.json and optimal_distance_tours.svg.

    Raises:
        OSError: The output directory or either report cannot be written.
    """
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    summary_path = output_directory / "optimal_distance_summary.json"
    svg_path = output_directory / "optimal_distance_tours.svg"
    summary_path.write_text(
        json.dumps(
            _summary_data(
                problem,
                solution,
                final_state_count,
                elapsed_seconds,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    svg_path.write_text(
        _render_svg(
            problem,
            solution,
            final_state_count,
            elapsed_seconds,
        ),
        encoding="utf-8",
    )
    return summary_path, svg_path


def _summary_data(
    problem: ProblemData,
    solution: Solution,
    final_state_count: int,
    elapsed_seconds: float,
) -> dict[str, object]:
    """Build the JSON-compatible summary for a minimum-distance report.

    Args:
        problem: Routing data identifying agents and appointments.
        solution: Evaluated routes to summarize.
        final_state_count: Number of states in the final DP layer.
        elapsed_seconds: Solver runtime in seconds.

    Returns:
        Overall distance and search statistics plus per-agent route summaries.
    """
    return {
        "objective": "minimum total distance",
        "total_distance_m": solution.metrics.total_distance,
        "final_dp_states": final_state_count,
        "elapsed_seconds": elapsed_seconds,
        "agents": {
            str(agent_id): _tour_data(
                problem,
                agent_id,
                tour,
                solution.tour_metrics[agent_id],
            )
            for agent_id, tour in enumerate(solution.tours)
        },
    }


def _tour_data(
    problem: ProblemData,
    agent_id: int,
    tour: Tour,
    metrics: TourMetrics,
) -> dict[str, object]:
    """Build a JSON-compatible summary of one agent's evaluated route.

    Args:
        problem: Routing data containing the agent's display name.
        agent_id: Agent associated with the route.
        tour: Node sequence including the two home endpoints.
        metrics: Previously evaluated metrics for this route.

    Returns:
        Agent name, node IDs, appointment count, distance in metres, travel
        time in seconds, and total gain.
    """
    appointments = tour[1:-1]
    return {
        "name": problem.agents[agent_id].name,
        "tour": tour,
        "appointments": appointments,
        "appointment_count": len(appointments),
        "distance_m": metrics.distance,
        "travel_time_s": metrics.travel_time,
        "gain": metrics.gain,
    }


def _render_svg(
    problem: ProblemData,
    solution: Solution,
    final_state_count: int,
    elapsed_seconds: float,
) -> str:
    """Render a geographic route overview and per-agent summaries as SVG.

    Project coordinates onto a simple local plane and draw straight segments
    between visits; the drawing does not represent road geometry. The problem
    must have nonzero latitude and longitude extents for the map scaling.

    Args:
        problem: Routing data with coordinates, agent names, and scheduled times.
        solution: Complete evaluated assignment to visualize.
        final_state_count: Number of states in the final DP layer.
        elapsed_seconds: Solver runtime in seconds.

    Returns:
        A standalone SVG document with routes colored by agent.

    Raises:
        ValueError: A home node has no associated agent ID.
    """
    width = 1600
    height = 980
    map_left = 55
    map_top = 100
    map_width = 970
    map_height = 810
    panel_left = 1060
    colors = [
        "#2563eb",
        "#dc2626",
        "#16a34a",
        "#9333ea",
        "#ea580c",
        "#0891b2",
        "#ca8a04",
    ]
    nodes = problem.nodes
    agents = problem.agents
    mean_latitude = sum(node.latitude for node in nodes) / len(nodes)
    longitude_scale = math.cos(math.radians(mean_latitude))
    projected = {
        node.id: (
            node.longitude * longitude_scale,
            node.latitude,
        )
        for node in nodes
    }
    min_x = min(point[0] for point in projected.values())
    max_x = max(point[0] for point in projected.values())
    min_y = min(point[1] for point in projected.values())
    max_y = max(point[1] for point in projected.values())
    scale = min(
        map_width / (max_x - min_x),
        map_height / (max_y - min_y),
    ) * 0.92
    used_width = (max_x - min_x) * scale
    used_height = (max_y - min_y) * scale
    offset_x = map_left + (map_width - used_width) / 2
    offset_y = map_top + (map_height - used_height) / 2

    def screen(node_id: int) -> tuple[float, float]:
        """Map one projected node to SVG pixel coordinates.

        Args:
            node_id: ID of a node already included in the projection.

        Returns:
            Horizontal and vertical pixel coordinates inside the map panel.
        """
        x, y = projected[node_id]
        return (
            offset_x + (x - min_x) * scale,
            offset_y + (max_y - y) * scale,
        )

    assignment = {
        node_id: agent_id
        for agent_id, tour in enumerate(solution.tours)
        for node_id in tour[1:-1]
    }
    svg = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        (
            '<style>text { font-family: -apple-system, BlinkMacSystemFont, '
            '"Segoe UI", sans-serif; }</style>'
        ),
        (
            '<text x="55" y="48" font-size="30" font-weight="700" '
            'fill="#0f172a">Exact minimum-distance tours</text>'
        ),
        (
            '<text x="55" y="77" font-size="17" fill="#475569">'
            f'Total distance: {solution.metrics.total_distance / 1000:.2f} km · '
            f'{len(assignment)} appointments · {len(solution.tours)} agents · '
            f'{final_state_count:,} final DP states · '
            f'{elapsed_seconds:.2f} s</text>'
        ),
        (
            f'<rect x="{map_left}" y="{map_top}" width="{map_width}" '
            f'height="{map_height}" rx="16" fill="#ffffff" '
            'stroke="#cbd5e1"/>'
        ),
    ]

    for agent_id, tour in enumerate(solution.tours):
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(screen, tour))
        color = colors[agent_id % len(colors)]
        svg.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" '
            'stroke-width="3" stroke-linejoin="round" '
            'stroke-linecap="round" opacity="0.72"/>'
        )

    for node in nodes:
        node_id = node.id
        x, y = screen(node_id)
        if node.kind == "home":
            if node.agent_id is None:
                raise ValueError(f"Home node {node.id} has no agent_id")
            agent_id = node.agent_id
            color = colors[agent_id % len(colors)]
            svg.extend(
                [
                    (
                        f'<rect x="{x - 8:.1f}" y="{y - 8:.1f}" '
                        f'width="16" height="16" rx="3" fill="{color}" '
                        'stroke="#ffffff" stroke-width="2"/>'
                    ),
                    (
                        f'<text x="{x + 11:.1f}" y="{y + 5:.1f}" '
                        'font-size="13" font-weight="700" fill="#0f172a">'
                        f'H{agent_id}</text>'
                    ),
                ]
            )
        else:
            agent_id = assignment[node_id]
            color = colors[agent_id % len(colors)]
            svg.extend(
                [
                    (
                        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" '
                        f'fill="{color}" stroke="#ffffff" stroke-width="2"/>'
                    ),
                    (
                        f'<text x="{x:.1f}" y="{y + 4:.1f}" '
                        'text-anchor="middle" font-size="9" '
                        f'font-weight="700" fill="#ffffff">{node_id}</text>'
                    ),
                ]
            )

    svg.extend(
        [
            (
                f'<rect x="{panel_left}" y="{map_top}" width="485" '
                f'height="{map_height}" rx="16" fill="#ffffff" '
                'stroke="#cbd5e1"/>'
            ),
            (
                f'<text x="{panel_left + 25}" y="{map_top + 38}" '
                'font-size="21" font-weight="700" fill="#0f172a">'
                'Per-agent summary</text>'
            ),
        ]
    )

    for agent_id, tour in enumerate(solution.tours):
        metrics = _tour_data(
            problem,
            agent_id,
            tour,
            solution.tour_metrics[agent_id],
        )
        color = colors[agent_id % len(colors)]
        y = map_top + 78 + agent_id * 100
        route_text = " → ".join(map(str, tour))
        appointment_times = [
            _format_time(nodes[node_id].time)
            for node_id in metrics["appointments"]
        ]
        time_text = (
            ", ".join(appointment_times)
            if appointment_times
            else "No appointments"
        )
        svg.extend(
            [
                (
                    f'<line x1="{panel_left + 25}" y1="{y}" '
                    f'x2="{panel_left + 60}" y2="{y}" stroke="{color}" '
                    'stroke-width="6" stroke-linecap="round"/>'
                ),
                (
                    f'<text x="{panel_left + 75}" y="{y + 6}" '
                    'font-size="17" font-weight="700" fill="#0f172a">'
                    f'{html.escape(agents[agent_id].name)}</text>'
                ),
                (
                    f'<text x="{panel_left + 25}" y="{y + 31}" '
                    'font-size="14" fill="#334155">'
                    f'{metrics["appointment_count"]} appointments · '
                    f'{metrics["distance_m"] / 1000:.2f} km · '
                    f'{metrics["travel_time_s"] / 60:.0f} min travel · '
                    f'gain {metrics["gain"]}</text>'
                ),
                (
                    f'<text x="{panel_left + 25}" y="{y + 53}" '
                    f'font-size="13" fill="#64748b">Nodes: {route_text}</text>'
                ),
                (
                    f'<text x="{panel_left + 25}" y="{y + 73}" '
                    f'font-size="13" fill="#64748b">Times: {time_text}</text>'
                ),
            ]
        )

    svg.extend(
        [
            (
                '<text x="55" y="948" font-size="13" fill="#64748b">'
                'Straight segments show visit order, not road geometry. '
                'Optimization uses D; feasibility uses appointment times, '
                'durations, T, startTime, and endTime.</text>'
            ),
            '</svg>',
        ]
    )
    return "\n".join(svg)


def _format_time(seconds: int) -> str:
    """Format seconds from midnight as HH:MM, discarding remaining seconds.

    Args:
        seconds: Time offset from midnight; hours may extend beyond 23.

    Returns:
        Hour and minute fields padded to at least two digits.
    """
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours:02}:{minutes:02}"
