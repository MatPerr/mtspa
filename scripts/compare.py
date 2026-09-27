import argparse
import time
from pathlib import Path

from app.optimization.datamodel import ProblemData, Solution
from app.optimization.objectives import LATENESS_PENALTY_PER_SECOND
from app.optimization.problem_io import load_data
from app.optimization.solvers.dp import DynamicProgrammingSolver
from app.optimization.solvers.sa import SimulatedAnnealingSolver


def format_table(rows: list[tuple[str, str, str, str]]) -> str:
    """Format metric comparisons as a left-aligned text table.

    Args:
        rows: Four-column rows containing metric label, DP value, SA value,
            and their displayed difference.

    Returns:
        A table with a header, separator, and columns sized to fit their content.
    """
    headers = ("Metric", "Dynamic programming", "Simulated annealing", "SA - DP")
    all_rows = [headers, *rows]
    widths = [
        max(len(row[column]) for row in all_rows)
        for column in range(len(headers))
    ]

    def format_row(row: tuple[str, str, str, str]) -> str:
        """Pad one row to the table's precomputed column widths.

        Args:
            row: Four strings in the same column order as the table header.

        Returns:
            A single row with columns separated by vertical bars.
        """
        return " | ".join(
            value.ljust(width)
            for value, width in zip(row, widths, strict=True)
        )

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join(
        [format_row(headers), separator]
        + [format_row(row) for row in rows]
    )


def comparison_rows(
    dp_solution: Solution,
    sa_solution: Solution,
    dp_elapsed: float,
    sa_elapsed: float,
) -> list[tuple[str, str, str, str]]:
    """Convert two solutions and runtimes into displayable comparison rows.

    Args:
        dp_solution: Evaluated dynamic-programming solution.
        sa_solution: Evaluated simulated-annealing solution.
        dp_elapsed: DP runtime in seconds.
        sa_elapsed: SA runtime in seconds.

    Returns:
        Metric, DP, SA, and SA-minus-DP columns, using kilometres and minutes
        for readability. Includes timing-feasibility flags and a distance gap
        percentage, which is zero when the DP distance is zero.
    """
    dp = dp_solution.metrics
    sa = sa_solution.metrics
    distance_gap = sa.total_distance - dp.total_distance
    distance_gap_percent = (
        distance_gap / dp.total_distance * 100
        if dp.total_distance > 0
        else 0.0
    )

    values = [
        (
            "Distance (km)",
            dp.total_distance / 1000,
            sa.total_distance / 1000,
            f"{distance_gap / 1000:+,.3f} ({distance_gap_percent:+.1f}%)",
            3,
        ),
        (
            "Distance std (km)",
            dp.distance_std / 1000,
            sa.distance_std / 1000,
            f"{(sa.distance_std - dp.distance_std) / 1000:+,.3f}",
            3,
        ),
        (
            "Travel time (min)",
            dp.total_travel_time / 60,
            sa.total_travel_time / 60,
            f"{(sa.total_travel_time - dp.total_travel_time) / 60:+,.1f}",
            1,
        ),
        (
            "Lateness (min)",
            dp.total_lateness / 60,
            sa.total_lateness / 60,
            f"{(sa.total_lateness - dp.total_lateness) / 60:+,.1f}",
            1,
        ),
        (
            "Waiting time (min)",
            dp.total_waiting_time / 60,
            sa.total_waiting_time / 60,
            f"{(sa.total_waiting_time - dp.total_waiting_time) / 60:+,.1f}",
            1,
        ),
        (
            "Waiting-time std (min)",
            dp.waiting_time_std / 60,
            sa.waiting_time_std / 60,
            f"{(sa.waiting_time_std - dp.waiting_time_std) / 60:+,.1f}",
            1,
        ),
        (
            "Overtime (min)",
            dp.total_overtime / 60,
            sa.total_overtime / 60,
            f"{(sa.total_overtime - dp.total_overtime) / 60:+,.1f}",
            1,
        ),
        (
            "Overtime std (min)",
            dp.overtime_std / 60,
            sa.overtime_std / 60,
            f"{(sa.overtime_std - dp.overtime_std) / 60:+,.1f}",
            1,
        ),
        (
            "Gain per km",
            dp.total_gain_per_km,
            sa.total_gain_per_km,
            f"{sa.total_gain_per_km - dp.total_gain_per_km:+,.3f}",
            3,
        ),
        (
            "Gain-per-km std",
            dp.gain_per_km_std,
            sa.gain_per_km_std,
            f"{sa.gain_per_km_std - dp.gain_per_km_std:+,.3f}",
            3,
        ),
        (
            "Gain per hour",
            dp.total_gain_per_hour,
            sa.total_gain_per_hour,
            f"{sa.total_gain_per_hour - dp.total_gain_per_hour:+,.3f}",
            3,
        ),
        (
            "Gain-per-hour std",
            dp.gain_per_hour_std,
            sa.gain_per_hour_std,
            f"{sa.gain_per_hour_std - dp.gain_per_hour_std:+,.3f}",
            3,
        ),
        (
            "Runtime (s)",
            dp_elapsed,
            sa_elapsed,
            f"{sa_elapsed - dp_elapsed:+,.3f}",
            3,
        ),
    ]

    rows = [
        (
            label,
            f"{dp_value:,.{decimals}f}",
            f"{sa_value:,.{decimals}f}",
            difference,
        )
        for label, dp_value, sa_value, difference, decimals in values
    ]
    rows.extend(
        [
            (
                "Appointments on time",
                "yes" if dp.total_lateness == 0 else "no",
                "yes" if sa.total_lateness == 0 else "no",
                "",
            ),
            (
                "Returns home on time",
                "yes" if dp.total_overtime == 0 else "no",
                "yes" if sa.total_overtime == 0 else "no",
                "",
            ),
        ]
    )
    return rows


def print_tours(
    problem: ProblemData,
    dp_solution: Solution,
    sa_solution: Solution,
) -> None:
    """Print each agent's DP and SA node sequences to the console.

    Args:
        problem: Routing data supplying agent names and IDs.
        dp_solution: DP routes in agent order.
        sa_solution: SA routes in the same agent order.

    Raises:
        ValueError: The numbers of agents and routes do not match.
    """
    print("\nTours")
    for agent, dp_tour, sa_tour in zip(
        problem.agents,
        dp_solution.tours,
        sa_solution.tours,
        strict=True,
    ):
        print(f"\n{agent.name} (agent {agent.id})")
        print(f"  DP: {' → '.join(map(str, dp_tour))}")
        print(f"  SA: {' → '.join(map(str, sa_tour))}")


def main() -> None:
    """Parse comparison options, run both solvers, and print metrics and routes."""
    parser = argparse.ArgumentParser(
        description="Run and compare the DP and simulated-annealing solvers"
    )
    parser.add_argument(
        "filepath",
        nargs="?",
        type=Path,
        default=Path("data/data.json"),
    )
    parser.add_argument("--steps", type=int, default=50_000)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--no-tours", action="store_true")
    arguments = parser.parse_args()

    if arguments.steps <= 0:
        parser.error("--steps must be positive")
    if arguments.runs <= 0:
        parser.error("--runs must be positive")

    problem = ProblemData(*load_data(arguments.filepath))

    print("Running dynamic programming...", flush=True)
    dp_solver = DynamicProgrammingSolver(problem)
    started = time.perf_counter()
    dp_solution = dp_solver.optimize()
    dp_elapsed = time.perf_counter() - started

    print(
        f"Running simulated annealing ({arguments.steps:,} steps, "
        f"{arguments.runs} run{'s' if arguments.runs != 1 else ''})...",
        flush=True,
    )
    sa_solver = SimulatedAnnealingSolver(problem, seed=arguments.seed)
    started = time.perf_counter()
    if arguments.runs == 1:
        sa_solution = sa_solver.optimize(
            steps=arguments.steps,
            show_progress=not arguments.no_progress,
        )
    else:
        sa_solution = sa_solver.optimize_parallel(
            steps=arguments.steps,
            n_runs=arguments.runs,
            show_progress=not arguments.no_progress,
        )
    sa_elapsed = time.perf_counter() - started

    print("\nObjectives")
    print("  DP: minimize distance subject to on-time appointments and return")
    print(
        "  SA: distance + "
        f"{LATENESS_PENALTY_PER_SECOND:,} × lateness in seconds"
    )
    print("\nComparison")
    print(
        format_table(
            comparison_rows(
                dp_solution,
                sa_solution,
                dp_elapsed,
                sa_elapsed,
            )
        )
    )

    if sa_solution.metrics.total_lateness or sa_solution.metrics.total_overtime:
        print(
            "\nInterpretation: SA is not feasible under the DP constraints, "
            "so its distance is not directly comparable with the feasible "
            "DP optimum."
        )
    else:
        distance_gap = (
            sa_solution.metrics.total_distance
            - dp_solution.metrics.total_distance
        )
        distance_gap_percent = (
            distance_gap / dp_solution.metrics.total_distance * 100
            if dp_solution.metrics.total_distance > 0
            else 0.0
        )
        print(
            "\nInterpretation: both solutions satisfy the DP constraints. "
            f"SA is {distance_gap / 1000:,.3f} km "
            f"({distance_gap_percent:.1f}%) above the exact distance optimum."
        )

    if not arguments.no_tours:
        print_tours(problem, dp_solution, sa_solution)


if __name__ == "__main__":
    main()
