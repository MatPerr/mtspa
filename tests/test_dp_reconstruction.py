import unittest

from app.optimization.datamodel import Agent, Node, ProblemData
from app.optimization.solvers.dp_reconstruction import reconstruct_tours


class TourReconstructionTests(unittest.TestCase):
    def setUp(self):
        """Create agents whose home node IDs differ from their agent IDs."""
        agents = [Agent(0, "Alice", 0, 1000), Agent(1, "Bob", 0, 1000)]
        nodes = [
            Node(0, 0, 0, 100, 10, "appointment", None, 1),
            Node(1, 0, 0, 0, 0, "home", 1, 0),
            Node(2, 0, 0, 200, 10, "appointment", None, 1),
            Node(3, 0, 0, 0, 0, "home", 0, 0),
            Node(4, 0, 0, 300, 10, "appointment", None, 1),
        ]
        costs = [[0] * 5 for _ in range(5)]
        self.problem = ProblemData(nodes, agents, costs, costs)

    def test_leading_zero_assignments_and_distinct_home_ids(self):
        """Decode agent sequence 0, 1, 0 without confusing agents and home nodes."""
        appointments = [0, 2, 4]
        tours = reconstruct_tours(self.problem, appointments, assignment_code=2)

        self.assertEqual(tours, [[3, 0, 4, 3], [1, 2, 1]])
        self.assertEqual(appointments, [0, 2, 4])
        self.assertEqual(self.problem.agent_home_nodes, [3, 1])

    def test_zero_code_still_assigns_every_appointment(self):
        """Keep all visits when every encoded assignment is to agent zero."""
        tours = reconstruct_tours(self.problem, [0, 2, 4], assignment_code=0)

        self.assertEqual(tours, [[3, 0, 2, 4, 3], [1, 1]])

    def test_no_appointments_returns_closed_empty_routes(self):
        """Return both home endpoints for each agent when there are no visits."""
        agents = [Agent(0, "Alice", 0, 1000), Agent(1, "Bob", 0, 1000)]
        nodes = [
            Node(0, 0, 0, 0, 0, "home", 1, 0),
            Node(1, 0, 0, 0, 0, "home", 0, 0),
        ]
        costs = [[0, 0], [0, 0]]
        problem = ProblemData(nodes, agents, costs, costs)

        self.assertEqual(reconstruct_tours(problem, [], assignment_code=0), [[1, 1], [0, 0]])

    def test_single_agent_preserves_supplied_appointment_order(self):
        """Handle a one-agent encoding even though its integer code is always zero."""
        nodes = [
            Node(0, 0, 0, 200, 10, "appointment", None, 1),
            Node(1, 0, 0, 0, 0, "home", 0, 0),
            Node(2, 0, 0, 100, 10, "appointment", None, 1),
        ]
        costs = [[0] * 3 for _ in range(3)]
        problem = ProblemData(nodes, [Agent(0, "Alice", 0, 1000)], costs, costs)

        self.assertEqual(reconstruct_tours(problem, [2, 0], assignment_code=0), [[1, 2, 0, 1]])


if __name__ == "__main__":
    unittest.main()
