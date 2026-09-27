import json
import random
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.optimization.datamodel import Agent, Node, ProblemData
from app.optimization.objectives import LOSS_CONFIGS, MetricName
from app.optimization.solvers.sa import SimulatedAnnealingSolver, optimize_for_loss_configs_parallel


class AnnealingHistoryTests(unittest.TestCase):
    def setUp(self):
        agents = [Agent(index, f"Agent {index}", 0, 1000) for index in range(2)]
        nodes = [Node(index, 0, 0, 0, 0, "home", index, 0) for index in range(2)]
        nodes.extend(
            Node(index, 0, 0, time, 10, "appointment", None, 1)
            for index, time in enumerate((100, 150, 200), start=2)
        )
        distances = [[abs(a - b) * 10 for b in range(5)] for a in range(5)]
        times = [[abs(a - b) for b in range(5)] for a in range(5)]
        self.problem = ProblemData(nodes, agents, distances, times)
        self.configs = (LOSS_CONFIGS["shortest_distance"], LOSS_CONFIGS["maximum_uptime"])
        self.weights = (
            {MetricName.TOTAL_DISTANCE: 1},
            {MetricName.TOTAL_DISTANCE: 1, MetricName.TOTAL_WAITING_TIME: 3},
        )

    def test_sampling_is_bounded_and_does_not_change_search(self):
        for steps in (1, 7, 137, 10_000):
            with self.subTest(steps=steps):
                solver = SimulatedAnnealingSolver(self.problem, seed=5, weights=self.weights[0])
                control = SimulatedAnnealingSolver(self.problem, seed=5, weights=self.weights[0])
                points, progress = [], []
                solution = solver.optimize(
                    steps, show_progress=False, history_callback=points.append,
                    progress_callback=lambda current, total: progress.append((current, total)),
                )
                self.assertEqual(solution, control.optimize(steps, show_progress=False))
                self.assertEqual(solver.rng.getstate(), control.rng.getstate())
                self.assertEqual(len(points), min(steps, 100) + 1)
                self.assertEqual(points[0].iteration, 0)
                self.assertEqual(points[-1].iteration, steps)
                self.assertEqual(points[-1].best_loss, solution.loss)
                self.assertEqual(progress[-1], (steps, steps))
                self.assertEqual(len({point.iteration for point in points}), len(points))
                self.assertEqual([point.iteration for point in points], sorted(point.iteration for point in points))
                self.assertTrue(all(point.current_loss >= point.best_loss for point in points))
                self.assertTrue(all(a.best_loss >= b.best_loss for a, b in zip(points, points[1:])))

    def test_history_tracks_accepted_current_loss_not_rejected_candidates(self):
        for draw, expected in ((0.99, [10, 10, 8, 8]), (0, [10, 20, 8, 12])):
            with self.subTest(random_draw=draw):
                solver = SimulatedAnnealingSolver(self.problem, seed=5, weights=self.weights[0])
                initial = replace(solver.initialize_solution(), loss=10)
                points = []
                with (
                    patch.object(solver, "initialize_solution", return_value=initial),
                    patch.object(solver, "evaluate_tours", side_effect=[
                        replace(initial, loss=loss) for loss in (20, 8, 12)
                    ]),
                    patch.object(solver.rng, "random", return_value=draw),
                    patch("app.optimization.solvers.sa.sample_neighbor", return_value=(initial.tours, (0, 1))),
                    patch("app.optimization.solvers.sa.calibrate_temperature", return_value=SimpleNamespace(
                        initial_temperature=1, cooling_rate=1,
                    )),
                ):
                    solution = solver.optimize(3, show_progress=False, history_callback=points.append)
                self.assertEqual([point.current_loss for point in points], expected)
                self.assertEqual([point.best_loss for point in points], [10, 10, 8, 8])
                self.assertEqual(solution.loss, 8)

    def test_no_moves_still_produces_a_flat_complete_history(self):
        solver = SimulatedAnnealingSolver(self.problem, seed=5, weights={})
        points = []
        with patch("app.optimization.solvers.sa.sample_neighbor", return_value=None):
            solution = solver.optimize(7, show_progress=False, history_callback=points.append)
        self.assertEqual(len(points), 8)
        self.assertTrue(all(point.current_loss == point.best_loss == solution.loss == 0 for point in points))

    def test_parallel_results_keep_the_winning_runs_history_for_each_config(self):
        master_rng = random.Random(7)
        seeds = [master_rng.getrandbits(64) for _ in range(2)]
        for with_progress in (False, True):
            with self.subTest(with_progress=with_progress):
                progress = []
                callback = (lambda current, total: progress.append((current, total))) if with_progress else None
                with (
                    patch("app.optimization.solvers.sa.ProcessPoolExecutor", ThreadPoolExecutor),
                    patch("app.optimization.solvers.sa.Manager") as manager,
                ):
                    manager.return_value.__enter__.return_value.Queue.side_effect = Queue
                    results = optimize_for_loss_configs_parallel(
                        self.problem, self.configs, 137, 2, seed=7, show_progress=False,
                        weights_by_config=self.weights, progress_callback=callback, record_history=True,
                    )
                self.assertEqual(tuple(result.config for result in results), self.configs)
                for result, weights in zip(results, self.weights, strict=True):
                    history = result.annealing_history
                    self.assertIsNotNone(history)
                    self.assertEqual(history.run_count, 2)
                    self.assertIn(history.run_number, (1, 2))
                    runs = []
                    for seed in seeds:
                        points = []
                        solution = SimulatedAnnealingSolver(self.problem, seed=seed, weights=weights).optimize(
                            137, show_progress=False, history_callback=points.append,
                        )
                        runs.append((solution, points))
                    self.assertEqual(result.solution.loss, min(solution.loss for solution, _ in runs))
                    self.assertEqual((result.solution, history.points), runs[history.run_number - 1])
                if with_progress:
                    self.assertEqual(progress[-1], (548, 548))

    def test_single_run_history_is_opt_in(self):
        for record_history in (False, True):
            with self.subTest(record_history=record_history):
                result, = optimize_for_loss_configs_parallel(
                    self.problem, self.configs[:1], 7, 1, seed=5, show_progress=False,
                    weights_by_config=self.weights[:1], record_history=record_history,
                )
                if record_history:
                    self.assertEqual(result.annealing_history.run_number, 1)
                    self.assertEqual(result.annealing_history.run_count, 1)
                    self.assertEqual(result.annealing_history.points[-1].best_loss, result.solution.loss)
                else:
                    self.assertIsNone(result.annealing_history)

    def test_api_and_stream_return_history_for_sa_only(self):
        payload = {
            "agents": [
                {"name": agent.name, "latitude": 0, "longitude": 0, "start_time": 0, "end_time": 1000}
                for agent in self.problem.agents
            ],
            "appointments": [
                {"latitude": 0, "longitude": 0, "time": node.time, "duration": node.duration, "gain": 1}
                for node in self.problem.nodes[2:]
            ],
            "steps": 7, "runs": 2, "seed": 5,
            "loss_config_ids": [config.id for config in self.configs],
        }
        with (
            TestClient(app) as client,
            patch("app.main.get_travel_matrices", new=AsyncMock(return_value=(
                self.problem.distances, self.problem.travel_times,
            ))),
            patch("app.optimization.solvers.sa.ProcessPoolExecutor", ThreadPoolExecutor),
            patch("app.optimization.solvers.sa.Manager") as manager,
        ):
            manager.return_value.__enter__.return_value.Queue.side_effect = Queue
            for solver in ("sa", "dp"):
                for endpoint in ("/api/solve", "/api/solve-stream"):
                    with self.subTest(solver=solver, endpoint=endpoint):
                        response = client.post(endpoint, json={**payload, "solver": solver})
                        self.assertEqual(response.status_code, 200, response.text)
                        if endpoint.endswith("-stream"):
                            events = [json.loads(line) for line in response.text.splitlines()]
                            self.assertEqual(events[-1]["type"], "result")
                            data = events[-1]["result"]
                            progress = [event for event in events if event["type"] == "progress"]
                            self.assertTrue(progress)
                            if solver == "sa":
                                self.assertEqual(progress[-1]["current"], 28)
                        else:
                            data = response.json()
                        self.assertEqual(len(data["solutions"]), 2)
                        for solution in data["solutions"]:
                            history = solution["annealing_history"]
                            if solver == "sa":
                                self.assertEqual(history["run_count"], 2)
                                self.assertEqual(history["points"][0]["iteration"], 0)
                                self.assertEqual(history["points"][-1]["iteration"], 7)
                                self.assertEqual(history["points"][-1]["best_loss"], solution["loss"])
                            else:
                                self.assertIsNone(history)


if __name__ == "__main__":
    unittest.main()
