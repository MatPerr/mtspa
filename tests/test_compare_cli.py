import subprocess
import sys
import unittest
from pathlib import Path

from app.optimization.datamodel import ProblemData
from app.optimization.objectives import MetricName
from app.optimization.problem_io import load_data
from app.optimization.solvers.sa import SimulatedAnnealingSolver


class ComparisonCliTests(unittest.TestCase):
    def test_demo_runs_and_reports_the_calibrated_lateness_weight(self):
        """Exercise the actual CLI and process workers, including its objective label."""
        root = Path(__file__).resolve().parents[1]
        dataset = root / "data/corsica_nurses.json"
        problem = ProblemData(*load_data(dataset))
        weight = SimulatedAnnealingSolver(problem, seed=0).weights[MetricName.TOTAL_LATENESS]

        for runs in (1, 2):
            with self.subTest(runs=runs):
                result = subprocess.run(
                    [
                        sys.executable, "-m", "scripts.compare", str(dataset),
                        "--steps", "40", "--runs", str(runs), "--seed", "0", "--no-progress", "--no-tours",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"SA: distance + {weight:,.3f} × lateness in seconds", result.stdout)
                self.assertIn("Interpretation:", result.stdout)


if __name__ == "__main__":
    unittest.main()
