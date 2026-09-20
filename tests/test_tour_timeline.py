import unittest

from app.optimization.datamodel import Agent, Node, ProblemData
from app.optimization.metrics import calculate_tour_metrics
from app.services.tour_timeline import build_tour_timeline


class TourTimelineTests(unittest.TestCase):
    def problem(self, appointments, travel_times, start=8 * 3_600, end=17 * 3_600):
        nodes = [Node(0, 48.0, 2.0, 0, 0, "home", 0, 0)]
        nodes.extend(
            Node(index, 48.0, 2.0, time, duration, "appointment", None, 10)
            for index, (time, duration) in enumerate(appointments, start=1)
        )
        return ProblemData(nodes, [Agent(0, "Alice", start, end)], travel_times, travel_times)

    def check_timeline(self, problem, tour):
        timeline = build_tour_timeline(problem, 0, tour, {node: node for node in problem.appointment_ids})
        metrics = calculate_tour_metrics(problem, 0, tour)
        for kind, field in [
            ("travel", "travel_time"),
            ("waiting", "waiting_time"),
            ("lateness", "lateness"),
            ("overtime", "overtime"),
        ]:
            with self.subTest(kind=kind):
                total = sum(s.end_time - s.start_time for s in timeline.segments if s.kind == kind)
                self.assertEqual(total, getattr(metrics, field))

        self.assertEqual(timeline.return_time, timeline.workday_start + metrics.elapsed_time)
        activity = sorted(
            (s for s in timeline.segments if s.kind not in ("lateness", "overtime") and s.end_time > s.start_time),
            key=lambda s: s.start_time,
        )
        self.assertEqual(activity[0].start_time, timeline.workday_start)
        self.assertEqual(activity[-1].end_time, timeline.end_time)
        for left, right in zip(activity, activity[1:]):
            self.assertEqual(left.end_time, right.start_time, "Activity must cover the day without gaps or overlap")
        return timeline

    def test_waiting_overlapping_lateness_overtime_and_zero_duration(self):
        problem = self.problem(
            [(9 * 3_600, 3_600), (9 * 3_600 + 1_800, 1_800), (9 * 3_600 + 2_700, 0)],
            [[0, 1_800, 0, 0], [0, 0, 1_800, 0], [0, 0, 0, 900], [3_600, 0, 0, 0]],
            end=11 * 3_600,
        )
        timeline = self.check_timeline(problem, [0, 1, 2, 3, 0])
        late = [s for s in timeline.segments if s.kind == "lateness"]
        self.assertEqual([(s.appointment_id, s.start_time, s.end_time) for s in late], [
            (2, 34_200, 37_800),
            (3, 35_100, 40_500),
        ])
        overtime = next(s for s in timeline.segments if s.kind == "overtime")
        self.assertEqual((overtime.start_time, overtime.end_time), (39_600, 44_100))
        marker = next(s for s in timeline.segments if s.kind == "appointment" and s.appointment_id == 3)
        self.assertEqual(marker.start_time, marker.end_time)
        self.assertFalse(any(s.kind == "available" for s in timeline.segments))

    def test_early_return_is_available_until_workday_end(self):
        problem = self.problem([(9 * 3_600, 1_800)], [[0, 1_800], [1_800, 0]])
        timeline = self.check_timeline(problem, [0, 1, 0])
        available = next(s for s in timeline.segments if s.kind == "available")
        self.assertEqual((available.start_time, available.end_time), (10 * 3_600, 17 * 3_600))
        self.assertFalse(any(s.kind in ("lateness", "overtime") for s in timeline.segments))

    def test_empty_tour(self):
        problem = self.problem([], [[0]])
        timeline = self.check_timeline(problem, [0, 0])
        self.assertEqual([s.kind for s in timeline.segments], ["available"])
        self.assertEqual(timeline.return_time, timeline.workday_start)

    def test_return_after_midnight_extends_the_timeline(self):
        problem = self.problem([(23 * 3_600, 7_200)], [[0, 3_600], [1_800, 0]], end=24 * 3_600)
        timeline = self.check_timeline(problem, [0, 1, 0])
        self.assertEqual(timeline.return_time, 25 * 3_600 + 1_800)
        self.assertEqual(timeline.end_time, timeline.return_time)

    def test_appointment_labels_use_display_ids(self):
        problem = self.problem([(9 * 3_600, 1_800)], [[0, 1_800], [1_800, 0]])
        timeline = build_tour_timeline(problem, 0, [0, 1, 0], {1: 7})
        appointment = next(s for s in timeline.segments if s.kind == "appointment")
        self.assertEqual(appointment.appointment_id, 7)


if __name__ == "__main__":
    unittest.main()
