import html
import json
import math
import textwrap
from dataclasses import asdict
from pathlib import Path

from app.optimization.datamodel import ProblemData, Solution, Tour, TourMetrics
from app.optimization.objectives import LossConfig, MetricName, SolverName


def save_solution_report(
    problem: ProblemData,
    solution: Solution,
    elapsed_seconds: float,
    output_directory: str | Path = "artifacts",
    *,
    solver: SolverName,
    loss_config: LossConfig,
    weights: dict[MetricName, float],
    run_settings: dict[str, int | None] | None = None,
) -> tuple[Path, Path]:
    """Write complete solution metrics, node data, and an SVG for either solver.

    Filenames include the solver and objective, so different methods/configs
    coexist. Repeating the same solver/config in one directory overwrites its
    two files. Metrics use dataclass field names and explicitly documented units.

    Args:
        problem: Routing data used for names, coordinates, and appointment times.
        solution: Evaluated solution to report.
        elapsed_seconds: Wall time of optimization, including all parallel runs
            when applicable, excluding input loading, loss-weight calibration
            and reporting. SA temperature calibration is part of optimization.
        output_directory: Directory receiving the JSON and SVG files.
        solver: Algorithm identifier; DP is exact and SA is approximate.
        loss_config: Objective selected for this result.
        weights: Calibrated weights actually used to score this solution.
        run_settings: Algorithm-specific settings/statistics, such as DP state
            counts or SA steps, run count and master seed.

    Returns:
        Paths to <solver>_<config>_summary.json and <solver>_<config>_tours.svg.

    Raises:
        OSError: The output directory or either report cannot be written.
    """
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    prefix = f"{solver}_{loss_config.id}"
    summary_path = output_directory / f"{prefix}_summary.json"
    svg_path = output_directory / f"{prefix}_tours.svg"
    summary_path.write_text(
        json.dumps(
            _summary_data(
                problem,
                solution,
                elapsed_seconds,
                solver,
                loss_config,
                weights,
                run_settings or {},
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
            elapsed_seconds,
            solver,
            loss_config,
            run_settings or {},
        ),
        encoding="utf-8",
    )
    return summary_path, svg_path


def _summary_data(
    problem: ProblemData,
    solution: Solution,
    elapsed_seconds: float,
    solver: SolverName,
    loss_config: LossConfig,
    weights: dict[MetricName, float],
    run_settings: dict[str, int | None],
) -> dict[str, object]:
    """Serialize the objective, metrics, and nodes needed to map every route."""
    return {
        "solver": solver,
        "method": "exact" if solver == "dp" else "approximate",
        "objective": {
            "id": loss_config.id,
            "name": loss_config.name,
            "description": loss_config.description,
            "importances": dict(loss_config.importances),
            "weights": dict(weights),
        },
        "loss": solution.loss,
        "elapsed_seconds": elapsed_seconds,
        "run_settings": run_settings,
        "units": {
            "distance": "metres",
            "time": "seconds",
            "coordinates": "WGS84 decimal degrees",
            "gain": "input gain units",
            "gain_per_km": "input gain units per kilometre",
            "gain_per_hour": "input gain units per elapsed hour",
        },
        "timing_feasible": solution.metrics.total_lateness == 0 and solution.metrics.total_overtime == 0,
        "metrics": asdict(solution.metrics),
        "nodes": {str(node.id): asdict(node) for node in problem.nodes},
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
        Agent name, ordered node IDs, appointment count and all TourMetrics.
    """
    appointments = tour[1:-1]
    return {
        "name": problem.agents[agent_id].name,
        "tour": tour,
        "appointments": appointments,
        "appointment_count": len(appointments),
        "metrics": asdict(metrics),
    }


def _render_svg(
    problem: ProblemData,
    solution: Solution,
    elapsed_seconds: float,
    solver: SolverName,
    loss_config: LossConfig,
    run_settings: dict[str, int | None],
) -> str:
    """Render a geographic route overview and per-agent summaries as SVG.

    Project coordinates onto a simple local plane and draw straight segments
    between visits; the drawing does not represent road geometry. Extend the
    canvas for large teams and wrap long route labels instead of clipping them.

    Args:
        problem: Routing data with coordinates, agent names, and scheduled times.
        solution: Complete evaluated assignment to visualize.
        elapsed_seconds: Solver runtime in seconds.
        solver: Algorithm identifier for the exact/approximate title.
        loss_config: Selected objective for the title.
        run_settings: DP state counts or SA iteration/run counts when supplied.

    Returns:
        A standalone SVG document with routes colored by agent.

    Raises:
        ValueError: A home node has no associated agent ID.
    """
    width = 1600
    map_left = 55
    map_top = 140
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
    cards = [
        (
            textwrap.wrap(agents[agent_id].name, width=38),
            _tour_lines(problem, tour, solution.tour_metrics[agent_id]),
        )
        for agent_id, tour in enumerate(solution.tours)
    ]
    card_heights = [24 * len(names) + 21 * len(lines) + 24 for names, lines in cards]
    panel_height = max(map_height, 70 + sum(card_heights))
    height = map_top + panel_height + 70
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
        map_width / max(max_x - min_x, 1e-9),
        map_height / max(max_y - min_y, 1e-9),
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
    solver_label = "Dynamic programming (exact)" if solver == "dp" else "Simulated annealing (approximate)"
    run_description = ""
    if solver == "dp" and "final_dp_states" in run_settings:
        run_description = f'{run_settings["final_dp_states"]:,} final DP states · '
    elif solver == "sa" and "steps" in run_settings and "runs" in run_settings:
        run_description = f'{run_settings["runs"]} runs × {run_settings["steps"]:,} steps · '
    metrics = solution.metrics
    timing_color = "#b91c1c" if metrics.total_lateness or metrics.total_overtime else "#475569"
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
            f'fill="#0f172a">{html.escape(solver_label)} — {html.escape(loss_config.name)}</text>'
        ),
        (
            '<text x="55" y="77" font-size="17" fill="#475569">'
            f'Total distance: {solution.metrics.total_distance / 1000:.2f} km · '
            f'{len(assignment)} appointments · {len(solution.tours)} agents · '
            f'{run_description}'
            f'{elapsed_seconds:.2f} s</text>'
        ),
        (
            f'<text x="55" y="106" font-size="17" fill="{timing_color}">'
            f'Lateness: {metrics.total_lateness / 60:.2f} min · '
            f'Waiting: {metrics.total_waiting_time / 60:.2f} min · '
            f'Overtime: {metrics.total_overtime / 60:.2f} min · '
            f'Loss: {solution.loss:.3f}</text>'
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
                f'height="{panel_height}" rx="16" fill="#ffffff" '
                'stroke="#cbd5e1"/>'
            ),
            (
                f'<text x="{panel_left + 25}" y="{map_top + 38}" '
                'font-size="21" font-weight="700" fill="#0f172a">'
                'Per-agent summary</text>'
            ),
        ]
    )

    y = map_top + 78
    for agent_id, ((name_lines, detail_lines), card_height) in enumerate(zip(cards, card_heights, strict=True)):
        color = colors[agent_id % len(colors)]
        svg.append(
            f'<line x1="{panel_left + 25}" y1="{y}" '
            f'x2="{panel_left + 60}" y2="{y}" stroke="{color}" '
            'stroke-width="6" stroke-linecap="round"/>'
        )
        for offset, name in enumerate(name_lines):
            svg.append(
                f'<text x="{panel_left + 75}" y="{y + 6 + 24 * offset}" '
                f'font-size="17" font-weight="700" fill="#0f172a">{html.escape(name)}</text>'
            )
        for offset, line in enumerate(detail_lines):
            line_y = y + 6 + 24 * len(name_lines) + 21 * offset
            svg.append(
                f'<text x="{panel_left + 25}" y="{line_y}" '
                f'font-size="13" fill="#475569">{html.escape(line)}</text>'
            )
        y += card_height

    svg.extend(
        [
            (
                f'<text x="55" y="{height - 28}" font-size="13" fill="#64748b">'
                'Straight segments show visit order, not road geometry. '
                'The selected objective uses calibrated metric weights; '
                'driving times do not model live traffic.</text>'
            ),
            '</svg>',
        ]
    )
    return "\n".join(svg)


def _tour_lines(problem: ProblemData, tour: Tour, metrics: TourMetrics) -> list[str]:
    """Format every per-tour metric and wrap visit IDs/times for the SVG panel."""
    appointments = tour[1:-1]
    times = ", ".join(_format_time(problem.nodes[node].time) for node in appointments) or "No appointments"
    lines = [
        f"{len(appointments)} appointments · {metrics.distance / 1000:.2f} km · "
        f"{metrics.travel_time / 60:.1f} min travel",
        f"Gain: {metrics.gain} · {metrics.gain_per_km:.2f}/km · {metrics.gain_per_hour:.2f}/h",
        f"Elapsed: {metrics.elapsed_time / 60:.1f} min · Waiting: {metrics.waiting_time / 60:.1f} min",
        f"Lateness: {metrics.lateness / 60:.2f} min · Overtime: {metrics.overtime / 60:.2f} min",
        "Nodes: " + " → ".join(map(str, tour)),
        "Scheduled times: " + times,
    ]
    return [part for line in lines for part in textwrap.wrap(line, width=56)]


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
