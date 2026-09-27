import gzip
import json
import math
import unittest
from collections import Counter
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.optimization.datamodel import ProblemData
from app.optimization.metrics import calculate_tour_metrics
from app.optimization.objectives import LOSS_CONFIGS
from app.optimization.problem_io import load_data
from app.optimization.solvers.dp import DEFAULT_MAX_STATES, DynamicProgrammingSolver
from app.optimization.solvers.sa import SimulatedAnnealingSolver
from app.services.problem_builder import build_problem
from app.services.samples import DATA_DIRECTORY, SAMPLES, load_sample
from scripts.generate_samples import GENERATORS, schedule_dinner_deliveries


class SampleDataTests(unittest.TestCase):
    def problem(self, sample_id):
        """Load one catalogued dataset as a validated routing problem.

        Args:
            sample_id: Identifier in the sample catalog.

        Returns:
            Problem data with saved matrices and precomputed feasibility lookups.
        """
        return ProblemData(*load_data(DATA_DIRECTORY / SAMPLES[sample_id][0]))

    def assert_complete_tours(self, problem, solution):
        """Assert exact appointment coverage and each agent's home endpoints.

        Args:
            problem: Routing problem defining appointments and agent homes.
            solution: Evaluated solution whose tours are checked.

        Raises:
            AssertionError: An appointment is missing or repeated, or a route
                starts or ends at the wrong home.
        """
        self.assertCountEqual(
            [node for tour in solution.tours for node in tour[1:-1]],
            problem.appointment_ids,
        )
        for home, tour in zip(problem.agent_home_nodes, solution.tours, strict=True):
            self.assertEqual((tour[0], tour[-1]), (home, home))

    def test_matrices_and_api_round_trip(self):
        """Check saved costs and reconstruct generated samples from API inputs."""
        for sample_id in SAMPLES:
            with self.subTest(sample_id=sample_id):
                problem = self.problem(sample_id)
                sample = load_sample(sample_id)
                for matrix in (problem.distances, problem.travel_times):
                    for node_id, row in enumerate(matrix):
                        self.assertEqual(row[node_id], 0)
                        self.assertTrue(all(isinstance(value, int) and value >= 0 for value in row))
                # The new files have homes first, in agent order, like the editor.
                if sample_id != "belgium":
                    rebuilt = build_problem(
                        sample.agents, sample.appointments, problem.distances, problem.travel_times,
                    )
                    self.assertEqual(rebuilt.nodes, problem.nodes)
                    self.assertEqual(rebuilt.agents, problem.agents)

    def test_generator_inputs_match_saved_samples(self):
        """Verify seeded generators reproduce the inputs of every saved sample."""
        for sample_id, generate in GENERATORS.items():
            with self.subTest(sample_id=sample_id):
                agents, appointments = generate()
                if sample_id == "paris_dinner_deliveries":
                    appointments, _ = schedule_dinner_deliveries(
                        agents, appointments, self.problem(sample_id).travel_times,
                    )
                sample = load_sample(sample_id)
                self.assertEqual(sample.agents, agents)
                self.assertEqual(sample.appointments, appointments)

    def test_corsica_has_two_agents_and_fifteen_visits(self):
        """Check Ajaccio agent counts, visit counts, and workday bounds."""
        problem = self.problem("corsica_nurses")
        self.assertEqual(len(problem.agents), 2)
        self.assertEqual(len(problem.appointment_ids), 15)
        self.assertEqual(problem.agent_start_times, [8 * 3600] * 2)
        self.assertEqual(problem.agent_end_times, [20 * 3600] * 2)

    def test_corsica_dp_is_feasible_for_both_configs(self):
        """Verify both supported DP objectives produce complete feasible Ajaccio tours."""
        problem = self.problem("corsica_nurses")
        solver = DynamicProgrammingSolver(problem, loss_configs=(
            LOSS_CONFIGS["shortest_distance"], LOSS_CONFIGS["maximum_uptime"],
        ))
        for result in solver.optimize_for_loss_configs():
            with self.subTest(config=result.config.id):
                self.assert_complete_tours(problem, result.solution)
                self.assertEqual(result.solution.metrics.total_lateness, 0)
                self.assertEqual(result.solution.metrics.total_overtime, 0)

    def test_harder_samples_have_verified_reference_tours(self):
        """Check saved reference tours cover every appointment without timing violations."""
        for sample_id in ("corsica_nurses", "paris_dinner_deliveries"):
            with self.subTest(sample_id=sample_id):
                path = DATA_DIRECTORY / SAMPLES[sample_id][0]
                opener = gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz" else path.open()
                with opener as file:
                    tours = json.load(file)["metadata"]["reference_tours"]
                problem = self.problem(sample_id)
                self.assertEqual(len(tours), len(problem.agents))
                self.assertCountEqual(
                    [node for tour in tours for node in tour[1:-1]], problem.appointment_ids,
                )
                for agent, tour in enumerate(tours):
                    home = problem.agent_home_nodes[agent]
                    self.assertEqual((tour[0], tour[-1]), (home, home))
                    metrics = calculate_tour_metrics(problem, agent, tour)
                    self.assertEqual(metrics.lateness, 0)
                    self.assertEqual(metrics.overtime, 0)

    def test_harder_samples_cannot_be_solved_by_nearest_home_clustering(self):
        """Verify nearest-home assignments cause lateness on the harder datasets."""
        for sample_id in ("corsica_nurses", "paris_dinner_deliveries"):
            with self.subTest(sample_id=sample_id):
                problem = self.problem(sample_id)
                tours = [[home] for home in problem.agent_home_nodes]
                for node in sorted(problem.appointment_ids, key=lambda node: (problem.node_times[node], node)):
                    agent = min(
                        range(len(problem.agents)),
                        key=lambda agent: problem.distances[problem.agent_home_nodes[agent]][node],
                    )
                    tours[agent].append(node)
                lateness = 0
                for agent, tour in enumerate(tours):
                    tour.append(problem.agent_home_nodes[agent])
                    lateness += calculate_tour_metrics(problem, agent, tour).lateness
                self.assertGreater(lateness, 0)

    def test_dinner_size_spread_and_staggered_times(self):
        """Check dinner delivery counts, geographic coverage, and staggered times."""
        problem = self.problem("paris_dinner_deliveries")
        self.assertEqual(len(problem.agents), 30)
        self.assertEqual(len(problem.appointment_ids), 300)
        self.assertEqual(problem.agent_start_times, [18 * 3600] * 30)
        self.assertEqual(problem.agent_end_times, [23 * 3600 + 30 * 60] * 30)
        nodes = [problem.nodes[node] for node in problem.appointment_ids]
        self.assertGreater(max(node.latitude for node in nodes) - min(node.latitude for node in nodes), 0.075)
        self.assertGreater(max(node.longitude for node in nodes) - min(node.longitude for node in nodes), 0.14)
        times = Counter(node.time for node in nodes)
        self.assertGreater(len(times), 100)
        self.assertLess(max(times.values()), 10)

    def test_paris_wave_structure_bounds_dp_states(self):
        """Check lunch delivery waves admit a DP layer bound below the default limit."""
        problem = self.problem("paris_deliveries")
        agent_count = len(problem.agents)
        self.assertEqual(agent_count, 8)
        self.assertEqual(len(problem.appointment_ids), 80)
        waves = Counter(problem.node_times[node_id] for node_id in problem.appointment_ids)
        self.assertEqual(len(waves), 10)
        self.assertTrue(all(size == agent_count for size in waves.values()))
        self.assertTrue(all(problem.node_durations[node_id] > 0 for node_id in problem.appointment_ids))
        # Every full wave uses every agent. During the next wave, each endpoint
        # is either in that wave or the preceding one: at most A! * C(A, k).
        peak_bound = math.factorial(agent_count) * math.comb(agent_count, agent_count // 2)
        self.assertEqual(peak_bound, 2_822_400)
        self.assertLess(peak_bound, DEFAULT_MAX_STATES)

    def test_paris_has_a_feasible_assignment_without_running_large_dp(self):
        """Verify the lunch sample's constructed assignment meets every timing constraint."""
        problem = self.problem("paris_deliveries")
        agent_count = len(problem.agents)
        for agent_id, home in enumerate(problem.agent_home_nodes):
            tour = [home, *problem.appointment_ids[agent_id::agent_count], home]
            metrics = calculate_tour_metrics(problem, agent_id, tour)
            self.assertEqual(metrics.lateness, 0)
            self.assertEqual(metrics.overtime, 0)

    def test_all_generated_samples_support_sa(self):
        """Smoke-test complete, finite-loss SA results on each generated sample."""
        for sample_id in GENERATORS:
            with self.subTest(sample_id=sample_id):
                problem = self.problem(sample_id)
                solution = SimulatedAnnealingSolver(problem, seed=0).optimize(200, show_progress=False)
                self.assert_complete_tours(problem, solution)
                self.assertTrue(math.isfinite(solution.loss))


class SampleApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_catalog_and_loading(self):
        """Verify every catalogued sample loads with the advertised input counts."""
        response = self.client.get("/api/samples")
        self.assertEqual(response.status_code, 200)
        samples = response.json()
        self.assertEqual({sample["id"] for sample in samples}, set(SAMPLES))
        for sample in samples:
            with self.subTest(sample_id=sample["id"]):
                response = self.client.get("/api/sample", params={"sample_id": sample["id"]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()["agents"]), sample["agent_count"])
                self.assertEqual(len(response.json()["appointments"]), sample["appointment_count"])

    def test_default_is_still_original_sample(self):
        """Verify the sample endpoint defaults to the original Belgium dataset."""
        default = self.client.get("/api/sample")
        self.assertEqual(default.json(), self.client.get("/api/sample?sample_id=belgium").json())

    def test_paris_sample_labels(self):
        """Verify the catalog distinguishes trivial lunch and difficult dinner samples."""
        names = {sample["id"]: sample["name"] for sample in self.client.get("/api/samples").json()}
        self.assertEqual(names["paris_deliveries"], "Paris - trivial lunch deliveries")
        self.assertEqual(names["paris_dinner_deliveries"], "Paris - difficult dinner deliveries")

    def test_dinner_can_be_solved_through_the_api(self):
        """Solve the dinner sample through the API while reusing saved driving costs."""
        sample = load_sample("paris_dinner_deliveries")
        problem = ProblemData(*load_data(DATA_DIRECTORY / SAMPLES["paris_dinner_deliveries"][0]))
        request = {**sample.model_dump(), "solver": "sa", "steps": 200, "runs": 1, "seed": 0}
        with patch(
            "app.main.get_travel_matrices", new_callable=AsyncMock,
            return_value=(problem.distances, problem.travel_times),
        ) as routing:
            response = self.client.post("/api/solve", json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(routing.call_args.args[0]), 330)
        tours = response.json()["solutions"][0]["tours"]
        self.assertEqual(len(tours), 30)
        self.assertCountEqual(
            [appointment for tour in tours for appointment in tour["appointment_ids"]],
            range(1, 301),
        )

    def test_unknown_samples_and_paths_are_rejected(self):
        """Verify arbitrary IDs and filesystem paths cannot select sample files."""
        for sample_id in ("missing", "../../README.md", "/etc/passwd"):
            response = self.client.get("/api/sample", params={"sample_id": sample_id})
            self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
