import json
import math
import random
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import asdict, fields, replace
from pathlib import Path

from app.optimization.datamodel import Agent, Node, ProblemData, Solution, SolutionMetrics, TourMetrics
from app.optimization.metrics import calculate_solution_metrics, calculate_tour_metrics
from app.optimization.objectives import LOSS_CONFIGS, MetricName, calculate_loss
from app.optimization.problem_io import load_data
from app.optimization.reporting import save_solution_report
from app.optimization.variation_ops import initialize_random_tours

ROOT = Path(__file__).resolve().parents[1]
SVG_TEXT = '{http://www.w3.org/2000/svg}text'


def evaluated_solution(problem, tours, weights):
    """Build a complete evaluated fixture without running an optimization."""
    tour_metrics = [calculate_tour_metrics(problem, agent, tour) for agent, tour in enumerate(tours)]
    metrics = calculate_solution_metrics(tour_metrics)
    return Solution(tours, tour_metrics, metrics, calculate_loss(metrics, weights))


class ReportingTests(unittest.TestCase):
    def setUp(self):
        """Create a small feasible problem with nonzero waiting and fairness metrics."""
        self.problem = ProblemData(
            nodes=[
                Node(0, 48.85, 2.35, 0, 0, 'home', 0, 0),
                Node(1, 48.86, 2.36, 0, 0, 'home', 1, 0),
                Node(2, 48.87, 2.37, 600, 60, 'appointment', None, 30),
                Node(3, 48.88, 2.38, 900, 60, 'appointment', None, 50),
            ],
            agents=[Agent(0, 'Camille & <équipe>', 0, 1800), Agent(1, 'Julien', 0, 1800)],
            distances=[[0 if i == j else 100 + i * 10 + j for j in range(4)] for i in range(4)],
            travel_times=[[0 if i == j else 50 for j in range(4)] for i in range(4)],
        )
        self.weights = {MetricName.TOTAL_DISTANCE: 1.0, MetricName.TOTAL_LATENESS: 100.0}
        self.tours = [[0, 2, 3, 0], [1, 1]]

    def export(self, directory, *, solver='sa', config_id='shortest_distance', problem=None, settings=None):
        """Export a fixture through the public shared reporter."""
        problem = problem or self.problem
        solution = evaluated_solution(problem, self.tours, self.weights)
        paths = save_solution_report(
            problem, solution, 1.25, directory,
            solver=solver, loss_config=LOSS_CONFIGS[config_id], weights=self.weights, run_settings=settings,
        )
        return solution, json.loads(paths[0].read_text()), ET.parse(paths[1]).getroot(), paths

    def test_json_preserves_all_metrics_and_actual_run_metadata(self):
        """Check full dataclass metrics, units, weights, identifiers and timing status."""
        settings = {'steps': 500, 'runs': 2, 'seed': 0}
        with tempfile.TemporaryDirectory() as directory:
            solution, summary, svg, _ = self.export(directory, settings=settings)
        self.assertEqual(summary['metrics'], asdict(solution.metrics))
        self.assertEqual(summary['objective']['weights'], self.weights)
        self.assertEqual(summary['objective']['importances'], LOSS_CONFIGS['shortest_distance'].importances)
        self.assertEqual(summary['loss'], solution.loss)
        self.assertEqual(summary['elapsed_seconds'], 1.25)
        self.assertEqual(summary['run_settings'], settings)
        self.assertEqual(summary['units']['distance'], 'metres')
        self.assertEqual(summary['units']['time'], 'seconds')
        self.assertEqual(summary['units']['coordinates'], 'WGS84 decimal degrees')
        self.assertEqual(summary['nodes'], {str(node.id): asdict(node) for node in self.problem.nodes})
        self.assertTrue(summary['timing_feasible'])
        for agent, tour in enumerate(solution.tours):
            reported = summary['agents'][str(agent)]
            self.assertEqual(reported['metrics'], asdict(solution.tour_metrics[agent]))
            self.assertEqual(reported['tour'], tour)
            self.assertEqual(reported['appointments'], tour[1:-1])
            self.assertEqual(reported['appointment_count'], len(tour) - 2)
        self.assertEqual(summary['agents']['0']['name'], 'Camille & <équipe>')
        self.assertIn('Camille & <équipe>', ''.join(svg.itertext()))

    def test_report_alone_resolves_routes_to_coordinates_and_home_owners(self):
        """Keep coordinates precise and resolve homes even when node and agent IDs differ."""
        nodes = [
            replace(node, agent_id=1 - node.agent_id) if node.kind == 'home' else node
            for node in self.problem.nodes
        ]
        nodes[0] = replace(nodes[0], latitude=48.850123456789, longitude=-2.350123456789)
        problem = ProblemData(nodes, self.problem.agents, self.problem.distances, self.problem.travel_times)
        self.tours = [[1, 2, 3, 1], [0, 0]]

        for solver in ('dp', 'sa'):
            with self.subTest(solver=solver), tempfile.TemporaryDirectory() as directory:
                _, summary, _, _ = self.export(directory, solver=solver, problem=problem)
                self.assertEqual(summary['nodes']['0']['latitude'], nodes[0].latitude)
                self.assertEqual(summary['nodes']['0']['longitude'], nodes[0].longitude)
                for agent_id, agent in summary['agents'].items():
                    route_nodes = [summary['nodes'][str(node_id)] for node_id in agent['tour']]
                    self.assertEqual(route_nodes[0], route_nodes[-1])
                    self.assertEqual(route_nodes[0]['kind'], 'home')
                    self.assertEqual(route_nodes[0]['agent_id'], int(agent_id))
                    self.assertEqual([node['id'] for node in route_nodes], agent['tour'])
                    for node in route_nodes:
                        self.assertIsInstance(node['latitude'], float)
                        self.assertIsInstance(node['longitude'], float)
                    for node in route_nodes[1:-1]:
                        self.assertEqual(node['kind'], 'appointment')
                        self.assertIsNone(node['agent_id'])

    def test_solver_and_objective_names_do_not_collide_or_mislabel_reports(self):
        """Every supported solver/config has unique files and the correct title."""
        with tempfile.TemporaryDirectory() as directory:
            for config in LOSS_CONFIGS.values():
                for solver in config.supported_solvers:
                    with self.subTest(solver=solver, config=config.id):
                        _, summary, svg, paths = self.export(directory, solver=solver, config_id=config.id)
                        self.assertEqual(paths[0].name, f'{solver}_{config.id}_summary.json')
                        self.assertEqual(paths[1].name, f'{solver}_{config.id}_tours.svg')
                        self.assertEqual(summary['solver'], solver)
                        self.assertEqual(summary['objective']['id'], config.id)
                        self.assertEqual(summary['objective']['name'], config.name)
                        method = 'exact' if solver == 'dp' else 'approximate'
                        self.assertEqual(summary['method'], method)
                        self.assertIn(f'({method}) — {config.name}', ''.join(svg.itertext()))
            self.assertEqual(len(list(Path(directory).iterdir())), 12)

    def test_infeasible_sa_result_keeps_lateness_overtime_and_warning(self):
        """A heuristic result must never be presented as on-time or exact by default."""
        problem = ProblemData(
            [replace(node, time=1) if node.kind == 'appointment' else node for node in self.problem.nodes],
            [replace(agent, end_time=100) for agent in self.problem.agents],
            self.problem.distances, self.problem.travel_times,
        )
        with tempfile.TemporaryDirectory() as directory:
            solution, summary, svg, _ = self.export(directory, problem=problem)
        self.assertGreater(solution.metrics.total_lateness, 0)
        self.assertGreater(solution.metrics.total_overtime, 0)
        self.assertEqual(summary['metrics'], asdict(solution.metrics))
        self.assertFalse(summary['timing_feasible'])
        self.assertNotIn('final_dp_states', summary['run_settings'])
        self.assertIn('Simulated annealing (approximate)', ''.join(svg.itertext()))
        warnings = [text for text in svg.iter(SVG_TEXT) if text.get('fill') == '#b91c1c']
        self.assertEqual(len(warnings), 1)
        self.assertIn(f'Lateness: {solution.metrics.total_lateness / 60:.2f}', warnings[0].text)
        self.assertIn(f'Overtime: {solution.metrics.total_overtime / 60:.2f}', warnings[0].text)

    def test_colocated_or_aligned_coordinates_produce_finite_svg(self):
        """Manual datasets may have zero geographic extent in one or both axes."""
        for same_latitude, same_longitude in [(True, False), (False, True), (True, True)]:
            with self.subTest(latitude=same_latitude, longitude=same_longitude):
                nodes = [replace(
                    node,
                    latitude=48.85 if same_latitude else node.latitude,
                    longitude=2.35 if same_longitude else node.longitude,
                ) for node in self.problem.nodes]
                problem = ProblemData(nodes, self.problem.agents, self.problem.distances, self.problem.travel_times)
                with tempfile.TemporaryDirectory() as directory:
                    _, _, svg, _ = self.export(directory, problem=problem)
                for element in svg.iter():
                    for key in ('x', 'y', 'cx', 'cy'):
                        if key in element.attrib:
                            self.assertTrue(math.isfinite(float(element.attrib[key])))
                    for point in element.attrib.get('points', '').split():
                        self.assertTrue(all(math.isfinite(float(value)) for value in point.split(',')))

    def test_large_team_and_long_routes_fit_in_svg_canvas(self):
        """The 30-agent SA sample must not clip later agents off a fixed-height canvas."""
        problem = ProblemData(*load_data(ROOT / 'data/paris_dinner_deliveries.json.gz'))
        tours = initialize_random_tours(problem, random.Random(0))
        solution = evaluated_solution(problem, tours, self.weights)
        with tempfile.TemporaryDirectory() as directory:
            _, path = save_solution_report(
                problem, solution, 2.0, directory,
                solver='sa', loss_config=LOSS_CONFIGS['shortest_distance'], weights=self.weights,
            )
            svg = ET.parse(path).getroot()
        height = float(svg.get('height'))
        self.assertGreater(height, 1000)
        for text in svg.iter(SVG_TEXT):
            self.assertLess(float(text.get('y')), height)
        rendered = ''.join(svg.itertext())
        for agent in problem.agents:
            self.assertIn(agent.name, rendered)


class ReportCliTests(unittest.TestCase):
    def test_both_clis_export_matching_schemas_for_selected_objectives(self):
        """Exercise real DP, single SA and process-pool SA entrypoints."""
        problem = ProblemData(*load_data(ROOT / 'data/corsica_nurses.json'))
        expected_nodes = {str(node.id): asdict(node) for node in problem.nodes}
        cases = [
            ('dp', 'shortest_distance', ['--max-states', '200000']),
            ('dp', 'maximum_uptime', ['--max-states', '200000']),
            ('sa', 'shortest_distance', ['--steps', '50', '--runs', '1', '--seed', '0']),
            ('sa', 'fair_distance', ['--steps', '50', '--runs', '2', '--seed', '0']),
        ]
        with tempfile.TemporaryDirectory() as directory:
            expected_keys = None
            for solver, config_id, options in cases:
                with self.subTest(solver=solver, config=config_id):
                    result = subprocess.run(
                        [
                            sys.executable, '-m', f'app.optimization.solvers.{solver}',
                            str(ROOT / 'data/corsica_nurses.json'), '--loss-config', config_id,
                            '--output', directory, *options,
                        ],
                        cwd=ROOT, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    prefix = f'{solver}_{config_id}'
                    summary_path = Path(directory) / f'{prefix}_summary.json'
                    svg_path = Path(directory) / f'{prefix}_tours.svg'
                    summary = json.loads(summary_path.read_text())
                    self.assertIn(str(summary_path), result.stdout)
                    self.assertIn(str(svg_path), result.stdout)
                    self.assertIn(f'Objective: {LOSS_CONFIGS[config_id].name}', result.stdout)
                    self.assertEqual(summary['objective']['id'], config_id)
                    self.assertEqual(summary['nodes'], expected_nodes)
                    self.assertEqual(set(summary['metrics']), {field.name for field in fields(SolutionMetrics)})
                    for agent in summary['agents'].values():
                        self.assertEqual(set(agent['metrics']), {field.name for field in fields(TourMetrics)})
                    expected_keys = expected_keys or set(summary)
                    self.assertEqual(set(summary), expected_keys)
                    expected_loss = sum(
                        weight * summary['metrics'][metric]
                        for metric, weight in summary['objective']['weights'].items()
                    )
                    self.assertAlmostEqual(summary['loss'], expected_loss)
                    self.assertGreaterEqual(summary['elapsed_seconds'], 0)
                    if solver == 'dp':
                        self.assertEqual(summary['run_settings']['max_states'], 200000)
                        self.assertGreater(summary['run_settings']['final_dp_states'], 0)
                        self.assertTrue(summary['timing_feasible'])
                    else:
                        self.assertEqual(summary['run_settings']['steps'], 50)
                        self.assertEqual(summary['run_settings']['runs'], int(options[3]))
                        self.assertEqual(summary['run_settings']['seed'], 0)
                        self.assertNotIn('final_dp_states', summary['run_settings'])
                    ET.parse(svg_path)


if __name__ == '__main__':
    unittest.main()
