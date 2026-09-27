import random
import subprocess
import sys
import unittest
from pathlib import Path

from app.optimization.datamodel import ProblemData
from app.optimization.problem_io import load_data
from app.optimization.solvers.dp import DynamicProgrammingSolver
from app.optimization.solvers.sa import SimulatedAnnealingSolver


class LiteCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.dataset = cls.root / "data/corsica_nurses.json"
        cls.problem = ProblemData(*load_data(cls.dataset))

    def run_cli(self, solver, *arguments):
        return subprocess.run(
            [sys.executable, "-m", f"app.optimization.solvers.{solver}_lite", str(self.dataset), *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def assert_solution_output(self, result, expected):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Loss: {expected.loss:.3f}", result.stdout)
        self.assertIn(f"Total distance: {expected.metrics.total_distance / 1000:.3f} km", result.stdout)
        self.assertIn(f"Total lateness: {expected.metrics.total_lateness} s", result.stdout)
        self.assertIn(f"Total overtime: {expected.metrics.total_overtime} s", result.stdout)
        self.assertIn("Elapsed:", result.stdout)
        for agent, tour in zip(self.problem.agents, expected.tours, strict=True):
            self.assertIn(f"  {agent.name}: {' -> '.join(map(str, tour))}", result.stdout)

    def test_dp_cli_matches_full_solver_and_prints_every_route(self):
        expected = DynamicProgrammingSolver(self.problem, max_states=200_000).optimize()
        result = self.run_cli("dp", "--max-states", "200000")
        self.assert_solution_output(result, expected)
        self.assertIn("(exact)", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_sa_step_progress_does_not_change_the_solution(self):
        expected = SimulatedAnnealingSolver(self.problem, seed=0).optimize(80, show_progress=False)
        for show_progress in (True, False):
            with self.subTest(show_progress=show_progress):
                options = [] if show_progress else ["--no-progress"]
                result = self.run_cli("sa", "--steps", "80", "--seed", "0", *options)
                self.assert_solution_output(result, expected)
                self.assertIn("(approximate)", result.stdout)
                if show_progress:
                    self.assertIn("SA steps:", result.stderr)
                    self.assertIn("80/80", result.stderr)
                else:
                    self.assertEqual(result.stderr, "")

    def test_parallel_sa_uses_independent_seeds_and_reports_completed_runs(self):
        master_rng = random.Random(0)
        solutions = [
            SimulatedAnnealingSolver(self.problem, seed=master_rng.getrandbits(64)).optimize(
                80, show_progress=False,
            )
            for _ in range(2)
        ]
        expected = min(solutions, key=lambda solution: solution.loss)
        for show_progress in (True, False):
            with self.subTest(show_progress=show_progress):
                options = [] if show_progress else ["--no-progress"]
                result = self.run_cli("sa", "--steps", "80", "--runs", "2", "--seed", "0", *options)
                self.assert_solution_output(result, expected)
                self.assertIn("2 run(s), 80 steps each", result.stdout)
                if show_progress:
                    self.assertIn("SA runs:", result.stderr)
                    self.assertIn("2/2", result.stderr)
                    self.assertNotIn("SA steps:", result.stderr)
                else:
                    self.assertEqual(result.stderr, "")

    def test_nonpositive_budgets_are_rejected(self):
        for solver, option in (("dp", "--max-states"), ("sa", "--steps"), ("sa", "--runs")):
            for value in ("0", "-1"):
                with self.subTest(solver=solver, option=option, value=value):
                    result = self.run_cli(solver, option, value)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("must be positive", result.stderr)
                    self.assertNotIn("Tours", result.stdout)

    def test_dp_state_limit_fails_without_printing_a_solution(self):
        result = self.run_cli("dp", "--max-states", "1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DP exceeded 1 states", result.stderr)
        self.assertNotIn("Tours", result.stdout)


if __name__ == "__main__":
    unittest.main()
