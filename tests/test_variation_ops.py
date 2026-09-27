import random
import unittest
from collections import Counter
from unittest.mock import Mock, patch

from app.optimization.datamodel import Agent, Node, ProblemData
from app.optimization.solvers.sa import SimulatedAnnealingSolver
from app.optimization.solvers.sa_lite import (
    SimulatedAnnealingSolver as LiteSimulatedAnnealingSolver,
)
from app.optimization.temperature_calibration import calibrate_temperature
from app.optimization.variation_ops import sample_neighbor, swap_appointments


class VariationOperatorTests(unittest.TestCase):
    def setUp(self):
        """Create three agents and paired appointments for swap and transfer checks."""
        agents = [Agent(i, f"Agent {i}", 0, 1000) for i in range(3)]
        nodes = [Node(i, 0, 0, 0, 0, "home", i, 0) for i in range(3)]
        nodes.extend(
            Node(i, 0, 0, scheduled_time, 10, "appointment", None, 1)
            for i, scheduled_time in enumerate([100, 100, 200, 200, 300, 300], 3)
        )
        distances = [[abs(a - b) * 10 for b in range(9)] for a in range(9)]
        travel_times = [[abs(a - b) for b in range(9)] for a in range(9)]
        self.problem = ProblemData(nodes, agents, distances, travel_times)
        self.tours = [[0, 3, 5, 7, 0], [1, 4, 6, 8, 1], [2, 2]]

    def test_same_time_swap_preserves_one_appointment_per_wave(self):
        """Verify same-time swaps preserve each route's scheduled-time distribution."""
        first, second = [tour.copy() for tour in self.tours[:2]]

        swap_appointments(self.problem, random.Random(0), first, second)

        self.assertNotEqual(first, self.tours[0])
        self.assertNotEqual(second, self.tours[1])
        for original, updated in zip(self.tours, [first, second]):
            self.assertEqual(
                Counter(self.problem.node_times[node] for node in original[1:-1]),
                Counter(self.problem.node_times[node] for node in updated[1:-1]),
            )
        self.assertCountEqual(first[1:-1] + second[1:-1], [3, 4, 5, 6, 7, 8])

    def test_different_time_swap_restores_chronological_order(self):
        """Verify swaps reinsert appointments by time with node ID as the tie-breaker."""
        first = [0, 3, 7, 0]
        second = [1, 5, 8, 1]
        rng = Mock(spec=random.Random)
        rng.randrange.side_effect = [1, 2]

        swap_appointments(self.problem, rng, first, second)

        self.assertEqual(first, [0, 7, 8, 0])
        self.assertEqual(second, [1, 3, 5, 1])

    def test_neighbors_preserve_inputs_and_support_incremental_metrics(self):
        """Check move invariants and compare incremental metrics with full evaluation."""
        original = [tour.copy() for tour in self.tours]
        solver = SimulatedAnnealingSolver(self.problem, seed=0)
        current = solver.build_solution(self.tours)
        observed_moves = set()

        for seed in range(100):
            neighbor, changed_agents = sample_neighbor(
                self.problem, random.Random(seed), self.tours,
            )
            self.assertEqual(self.tours, original)
            self.assertCountEqual(
                [node for tour in neighbor for node in tour[1:-1]],
                self.problem.appointment_ids,
            )
            for agent, tour in enumerate(neighbor):
                self.assertEqual((tour[0], tour[-1]), (agent, agent))
                self.assertEqual(
                    tour[1:-1],
                    sorted(tour[1:-1], key=lambda node: (self.problem.node_times[node], node)),
                )
                if agent in changed_agents:
                    self.assertIsNot(tour, self.tours[agent])
                else:
                    self.assertEqual(tour, self.tours[agent])

            donor = changed_agents[0]
            observed_moves.add(
                "swap" if len(neighbor[donor]) == len(self.tours[donor]) else "transfer"
            )
            self.assertEqual(
                solver.build_solution(neighbor, previous=current, changed_agent_ids=changed_agents),
                solver.build_solution(neighbor),
            )

        self.assertEqual(observed_moves, {"swap", "transfer"})

    def test_empty_receiver_uses_transfer(self):
        """Verify a pair with one empty route moves an appointment into that route."""
        tours = [[0, 3, 0], [1, 1], [2, 2]]
        rng = Mock(spec=random.Random)
        rng.sample.return_value = [1, 0]
        rng.randrange.return_value = 1

        neighbor, changed_agents = sample_neighbor(self.problem, rng, tours)

        self.assertEqual(neighbor, [[0, 0], [1, 3, 1], [2, 2]])
        self.assertEqual(changed_agents, (0, 1))
        self.assertEqual(tours, [[0, 3, 0], [1, 1], [2, 2]])

    def test_two_empty_tours_have_no_neighbor(self):
        """Verify selecting two empty routes produces no proposed move."""
        tours = [[0, 3, 0], [1, 1], [2, 2]]
        rng = Mock(spec=random.Random)
        rng.sample.return_value = [1, 2]

        self.assertIsNone(sample_neighbor(self.problem, rng, tours))

    def test_full_and_lite_solvers_use_the_same_search(self):
        """Verify seeded full and lite SA searches return identical solutions."""
        full = SimulatedAnnealingSolver(self.problem, seed=0).optimize(
            200, show_progress=False,
        )
        lite = LiteSimulatedAnnealingSolver(self.problem, seed=0).optimize(200)

        self.assertEqual(full, lite)

    def test_equal_cost_neighbors_allow_temperature_calibration(self):
        """Verify equal-cost proposals still yield positive cooling temperatures."""
        solver = SimulatedAnnealingSolver(self.problem, seed=0)
        current = solver.build_solution(self.tours)

        with patch(
            "app.optimization.temperature_calibration.sample_neighbor",
            return_value=(self.tours, (0, 1)),
        ):
            config = calibrate_temperature(
                self.problem, random.Random(0), current, solver.weights, 1,
            )

        self.assertGreater(config.final_temperature, 0)
        self.assertGreater(config.initial_temperature, config.final_temperature)
        self.assertGreater(config.cooling_rate, 0)
        self.assertLess(config.cooling_rate, 1)


if __name__ == "__main__":
    unittest.main()
