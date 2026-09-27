import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.optimization.datamodel import Agent, Node, ProblemData
from app.optimization.loss_calibration import (
    calibrate_loss_weights,
    calibrate_loss_weights_for_configs,
    estimate_metric_scales,
)
from app.optimization.metrics import calculate_solution_metrics, calculate_tour_metrics
from app.optimization.objectives import LOSS_CONFIGS, MetricName, calculate_loss
from app.optimization.solvers.dp import DynamicProgrammingSolver
from app.optimization.solvers.dp_lite import DynamicProgrammingSolver as LiteDPSolver
from app.optimization.solvers.sa import (
    SimulatedAnnealingSolver,
    optimize_for_loss_configs_parallel,
)
from app.optimization.solvers.sa_lite import SimulatedAnnealingSolver as LiteSASolver


class LossCalibrationTests(unittest.TestCase):
    def setUp(self):
        """Build a small feasible routing problem with nonzero waiting times."""
        agents = [Agent(index, f"Agent {index}", 0, 1000) for index in range(2)]
        nodes = [Node(index, 0, 0, 0, 0, "home", index, 0) for index in range(2)]
        nodes.extend(
            Node(index, 0, 0, time, 10, "appointment", None, 1)
            for index, time in enumerate((100, 150, 200), start=2)
        )
        distances = [[abs(a - b) * 10 for b in range(5)] for a in range(5)]
        times = [[abs(a - b) for b in range(5)] for a in range(5)]
        self.problem = ProblemData(nodes, agents, distances, times)
        self.tours = [[0, 2, 4, 0], [1, 3, 1]]
        self.metrics = calculate_solution_metrics([
            calculate_tour_metrics(self.problem, agent, tour)
            for agent, tour in enumerate(self.tours)
        ])

    def test_calibration_preserves_preferences_and_scores_raw_metrics(self):
        """Verify typical-change priorities become the expected raw-unit penalties."""
        config = LOSS_CONFIGS["shortest_distance"]
        original = config.importances.copy()
        scales = {MetricName.TOTAL_DISTANCE: 1000, MetricName.TOTAL_LATENESS: 60}
        with patch(
            "app.optimization.loss_calibration.estimate_metric_scales",
            return_value=scales,
        ):
            weights = calibrate_loss_weights(self.problem, config.importances)

        self.assertEqual(weights, {MetricName.TOTAL_DISTANCE: 1, MetricName.TOTAL_LATENESS: 195})
        self.assertEqual(config.importances, original)
        on_time = replace(self.metrics, total_distance=10000, total_lateness=0)
        shorter_but_late = replace(self.metrics, total_distance=9000, total_lateness=10)
        self.assertEqual(calculate_loss(on_time, weights), 10000)
        self.assertEqual(calculate_loss(shorter_but_late, weights), 10950)

    def test_multiple_configs_share_one_walk_and_keep_their_order(self):
        """Verify batch calibration samples the metric union once and preserves order."""
        configs = (LOSS_CONFIGS["maximum_uptime"], LOSS_CONFIGS["shortest_distance"])
        scales = {
            MetricName.TOTAL_DISTANCE: 1000,
            MetricName.TOTAL_LATENESS: 60,
            MetricName.TOTAL_WAITING_TIME: 200,
        }
        with patch(
            "app.optimization.loss_calibration.estimate_metric_scales",
            return_value=scales,
        ) as estimate:
            weights = calibrate_loss_weights_for_configs(self.problem, iter(configs))
            self.assertEqual(calibrate_loss_weights_for_configs(self.problem, ()), ())

        estimate.assert_called_once_with(self.problem, set(scales))
        self.assertAlmostEqual(weights[0][MetricName.TOTAL_WAITING_TIME], 2.6715)
        self.assertNotIn(MetricName.TOTAL_WAITING_TIME, weights[1])
        self.assertEqual(weights[1], {MetricName.TOTAL_DISTANCE: 1, MetricName.TOTAL_LATENESS: 195})

    def test_supplied_weights_skip_calibration_and_are_copied(self):
        """Verify explicit weights, including empty ones, remain isolated from callers."""
        with patch(
            "app.optimization.loss_calibration.estimate_metric_scales",
            side_effect=AssertionError("Supplied weights must skip calibration"),
        ):
            for solver_type in (SimulatedAnnealingSolver, LiteSASolver, LiteDPSolver):
                for original in ({}, {MetricName.TOTAL_DISTANCE: 2}):
                    with self.subTest(solver=solver_type.__module__, weights=original):
                        supplied = original.copy()
                        solver = solver_type(self.problem, weights=supplied)
                        supplied[MetricName.TOTAL_WAITING_TIME] = 999
                        solution = solver.build_solution(self.tours)
                        self.assertEqual(solver.weights, original)
                        self.assertEqual(solution.loss, calculate_loss(solution.metrics, original))

    def test_parallel_runs_reuse_the_parent_weights(self):
        """Verify full and lite worker runs inherit weights without another walk."""
        weights = {MetricName.TOTAL_DISTANCE: 2, MetricName.TOTAL_LATENESS: 17}
        with (
            patch("app.optimization.solvers.sa.ProcessPoolExecutor", ThreadPoolExecutor),
            patch("app.optimization.solvers.sa_lite.ProcessPoolExecutor", ThreadPoolExecutor),
            patch(
                "app.optimization.loss_calibration.estimate_metric_scales",
                side_effect=AssertionError("Workers must reuse their parent's weights"),
            ),
        ):
            full = SimulatedAnnealingSolver(self.problem, seed=7, weights=weights)
            lite = LiteSASolver(self.problem, seed=7, weights=weights)
            solutions = (
                full.optimize_parallel(40, 2, show_progress=False),
                lite.optimize_parallel(40, 2),
            )
        for solution in solutions:
            self.assertEqual(solution.loss, calculate_loss(solution.metrics, weights))

    def test_parallel_objectives_calibrate_once_for_all_runs(self):
        """Verify multi-objective jobs share calibration and retain the right scores."""
        configs = (LOSS_CONFIGS["maximum_uptime"], LOSS_CONFIGS["shortest_distance"])
        expected_weights = calibrate_loss_weights_for_configs(self.problem, configs)
        with (
            patch("app.optimization.solvers.sa.ProcessPoolExecutor", ThreadPoolExecutor),
            patch(
                "app.optimization.loss_calibration.estimate_metric_scales",
                wraps=estimate_metric_scales,
            ) as estimate,
        ):
            results = optimize_for_loss_configs_parallel(
                self.problem, configs, 40, 2, seed=7, show_progress=False,
            )
        estimate.assert_called_once()
        self.assertEqual(tuple(result.config for result in results), configs)
        for result, weights in zip(results, expected_weights, strict=True):
            self.assertEqual(result.solution.loss, calculate_loss(result.solution.metrics, weights))

    def test_dp_matches_lite_for_each_objective(self):
        """Verify DP reconstruction and scoring use the weights of each objective."""
        configs = (LOSS_CONFIGS["maximum_uptime"], LOSS_CONFIGS["shortest_distance"])
        solver = DynamicProgrammingSolver(self.problem, loss_configs=configs)
        results = solver.optimize_for_loss_configs()
        for result, config in zip(results, configs, strict=True):
            expected = LiteDPSolver(self.problem, loss_config=config).optimize()
            self.assertEqual(result.config, config)
            self.assertEqual(result.solution, expected)

    def test_parallel_weights_must_match_config_count(self):
        """Reject supplied weights that cannot be paired with the selected configs."""
        with self.assertRaisesRegex(ValueError, "one weight dictionary per loss config"):
            optimize_for_loss_configs_parallel(
                self.problem, (LOSS_CONFIGS["shortest_distance"],), 40, 1,
                show_progress=False, weights_by_config=(),
            )

    def test_catalog_preserves_the_frontend_response_format(self):
        """Verify dictionary-based configs still expose the existing API term lists."""
        with TestClient(app) as client:
            response = client.get("/api/loss-configs")
        self.assertEqual(response.status_code, 200)
        shortest = next(config for config in response.json() if config["id"] == "shortest_distance")
        self.assertEqual(shortest["supported_solvers"], ["sa", "dp"])
        self.assertEqual(shortest["terms"], [
            {"metric": "total_distance", "importance": 1},
            {"metric": "total_lateness", "importance": 11.7},
        ])


if __name__ == "__main__":
    unittest.main()
