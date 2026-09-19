import argparse
import time
from pathlib import Path

from DP import DynamicProgrammingSolver
from SA import SimulatedAnnealingSolver
from datamodel import ProblemData, Solution
from utils import LATENESS_PENALTY_PER_SECOND, load_data


def format_table(rows: list[tuple[str, str, str, str]]) -> str:
    headers = ("Metric", "Dynamic programming", "Simulated annealing", "SA - DP")
    all_rows = [headers, *rows]
    widths = [
        max(len(row[column]) for row in all_rows)
        for column in range(len(headers))
    ]

    def format_row(row: tuple[str, str, str, str]) -> str:
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
            dp.total_time / 60,
            sa.total_time / 60,
            f"{(sa.total_time - dp.total_time) / 60:+,.1f}",
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
    parser.add_argument("--p", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--no-tours", action="store_true")
    arguments = parser.parse_args()

    if arguments.steps <= 0:
        parser.error("--steps must be positive")
    if arguments.runs <= 0:
        parser.error("--runs must be positive")
    if not 0 <= arguments.p <= 1:
        parser.error("--p must be between 0 and 1")

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
            p=arguments.p,
            show_progress=not arguments.no_progress,
        )
    else:
        sa_solution = sa_solver.optimize_parallel(
            steps=arguments.steps,
            n_runs=arguments.runs,
            p=arguments.p,
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
