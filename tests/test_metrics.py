import unittest
from unittest.mock import call, patch

from app.optimization.datamodel import Agent, Node, ProblemData
from app.optimization.metrics import (
    calculate_metrics,
    calculate_solution_metrics,
    calculate_tour_metrics,
)
from app.optimization.solvers.sa import SimulatedAnnealingSolver
from app.optimization.solvers.sa_lite import SimulatedAnnealingSolver as LiteSASolver


class CalculateMetricsTests(unittest.TestCase):
    def setUp(self):
        agents = [Agent(i, f"Agent {i}", 0, 400) for i in range(3)]
        nodes = [Node(i, 0, 0, 0, 0, "home", i, 0) for i in range(3)]
        nodes.extend(
            Node(i, 0, 0, scheduled_time, 20, "appointment", None, 10)
            for i, scheduled_time in enumerate((100, 150, 300), 3)
        )
        distances = [[abs(a - b) * 100 for b in range(6)] for a in range(6)]
        times = [[abs(a - b) * 10 for b in range(6)] for a in range(6)]
        self.problem = ProblemData(nodes, agents, distances, times)
        self.tours = [[0, 3, 5, 0], [1, 4, 1], [2, 2]]
        self.previous_metrics = self.route_metrics(self.tours)

    def route_metrics(self, tours):
        return [calculate_tour_metrics(self.problem, agent, tour) for agent, tour in enumerate(tours)]

    def test_full_evaluation_calculates_every_tour(self):
        original_tours = [tour.copy() for tour in self.tours]
        with patch("app.optimization.metrics.calculate_tour_metrics", wraps=calculate_tour_metrics) as calculate:
            metrics_by_tour, metrics = calculate_metrics(self.problem, self.tours)

        self.assertEqual(calculate.call_args_list, [
            call(self.problem, agent, tour) for agent, tour in enumerate(self.tours)
        ])
        self.assertEqual(metrics_by_tour, self.previous_metrics)
        self.assertEqual(metrics, calculate_solution_metrics(self.previous_metrics))
        self.assertEqual(self.tours, original_tours)

    def test_incremental_evaluation_reuses_unchanged_records_without_mutation(self):
        tours = [[0, 3, 0], [1, 4, 5, 1], [2, 2]]
        original_tours = [tour.copy() for tour in tours]
        original_metrics = self.previous_metrics.copy()
        expected = self.route_metrics(tours)
        with patch("app.optimization.metrics.calculate_tour_metrics", wraps=calculate_tour_metrics) as calculate:
            metrics_by_tour, metrics = calculate_metrics(
                self.problem, tours, previous_metrics=self.previous_metrics, changed_agent_ids=(0, 1),
            )

        self.assertEqual(calculate.call_args_list, [call(self.problem, 0, tours[0]), call(self.problem, 1, tours[1])])
        self.assertEqual(metrics_by_tour, expected)
        self.assertEqual(metrics, calculate_solution_metrics(expected))
        self.assertIsNot(metrics_by_tour, self.previous_metrics)
        self.assertIs(metrics_by_tour[2], self.previous_metrics[2])
        self.assertEqual(self.previous_metrics, original_metrics)
        self.assertEqual(tours, original_tours)

    def test_empty_changed_ids_reuses_all_records(self):
        with patch("app.optimization.metrics.calculate_tour_metrics") as calculate:
            metrics_by_tour, metrics = calculate_metrics(
                self.problem, self.tours, previous_metrics=self.previous_metrics, changed_agent_ids=(),
            )

        calculate.assert_not_called()
        self.assertIsNot(metrics_by_tour, self.previous_metrics)
        for previous, current in zip(self.previous_metrics, metrics_by_tour, strict=True):
            self.assertIs(previous, current)
        self.assertEqual(metrics, calculate_solution_metrics(self.previous_metrics))

    def test_all_changed_ids_matches_full_recalculation(self):
        tours = [[0, 0], [1, 3, 1], [2, 4, 5, 2]]
        expected = self.route_metrics(tours)
        result = calculate_metrics(
            self.problem, tours, previous_metrics=self.previous_metrics, changed_agent_ids=(0, 1, 2),
        )
        self.assertEqual(result, (expected, calculate_solution_metrics(expected)))

    def test_cache_and_changed_ids_must_be_supplied_together(self):
        cases = [
            {"changed_agent_ids": ()},
            {"changed_agent_ids": (0,)},
            {"previous_metrics": self.previous_metrics},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with patch("app.optimization.metrics.calculate_tour_metrics") as calculate:
                    with self.assertRaises(ValueError):
                        calculate_metrics(self.problem, self.tours, **arguments)
                calculate.assert_not_called()

    def test_sa_callers_preserve_validation_and_incremental_results(self):
        for solver_type in (SimulatedAnnealingSolver, LiteSASolver):
            with self.subTest(solver=solver_type.__module__):
                solver = solver_type(self.problem, seed=0, weights={})
                previous = solver.build_solution(self.tours)
                with self.assertRaises(ValueError):
                    solver.build_solution(self.tours, changed_agent_ids=())
                with self.assertRaises(ValueError):
                    solver.build_solution(self.tours, previous=previous)
                self.assertEqual(
                    solver.build_solution(self.tours, previous=previous, changed_agent_ids=()),
                    previous,
                )


if __name__ == "__main__":
    unittest.main()
