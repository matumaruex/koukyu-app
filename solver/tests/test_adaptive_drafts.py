"""不足許可、計算段階の切替、元の表がある場合の早期終了を確認する。"""
import threading
import time
import unittest
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve, _FirstSolution, _solve_with_stop_rule
from solver.validator import validate
from solver.tests.test_engine import fixture
from solver.tests.test_requested_night_rest import fixture as preference_fixture


class WaitingSolver:
    """候補が届かない段階でも監視が止められることを確認する。"""
    def __init__(self, seconds=0.8):
        self.done = threading.Event()
        self.seconds = seconds

    def solve(self, model, tracker):
        self.done.wait(self.seconds)
        return cp_model.UNKNOWN

    def stop_search(self):
        self.done.set()


class AdaptiveDraftTests(unittest.TestCase):
    def test_shared_first_candidate_stops_a_phase_without_new_candidates(self):
        tracker = _FirstSolution()
        start = time.monotonic() - 0.25
        tracker.first = start + 0.02
        solver = WaitingSolver()
        status, early, first = _solve_with_stop_rule(
            solver, None, 0.3, 0.2, tracker=tracker, start=start)
        self.assertEqual(status, cp_model.UNKNOWN)
        self.assertTrue(early)
        self.assertAlmostEqual(first, 0.02, places=2)
        self.assertLess(time.monotonic() - start, 0.7)

    def test_without_any_candidate_does_not_stop_early(self):
        solver = WaitingSolver(0.25)
        _, early, first = _solve_with_stop_rule(solver, None, 0.02, 0.02)
        self.assertFalse(early)
        self.assertIsNone(first)

    def test_normal_shortfall_returns_a_checked_table_early(self):
        raw = fixture(3)
        result = solve(raw, seconds=60, min_seconds=3, after_first=1,
                       allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertIn(result['status'], ('DRAFT', 'FEASIBLE', 'OPTIMAL'))
        errors = validate(raw, result['assignments'])
        self.assertTrue(all(e['code'] in ('coverage', 'sunday_limit', 'night_coverage') for e in errors))
        self.assertLess(result['seconds'], 30)
        self.assertEqual(result['timing']['mode'], 'adaptive')
        self.assertIsNotNone(result['stopRule']['firstSolutionSeconds'])
        if result.get('solverStatus', result['status']) != 'OPTIMAL':
            self.assertTrue(result['stopRule']['stoppedEarly'])
            self.assertEqual(result['timing']['reason'], 'early_return')

    def test_two_phases_share_the_start_and_first_candidate(self):
        raw = preference_fixture()
        before = solve(raw, seconds=3, optimize=False)
        self.assertIn('assignments', before)
        raw['locked'] = before['assignments']
        calls = []

        def recorded(*args, **kwargs):
            calls.append((kwargs['start'], kwargs['tracker']))
            return _solve_with_stop_rule(*args, **kwargs)

        with patch('solver.engine._solve_with_stop_rule', side_effect=recorded):
            result = solve(raw, seconds=12, min_seconds=2, after_first=1,
                           allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertIn(result['status'], ('DRAFT', 'FEASIBLE', 'OPTIMAL'))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(start == calls[0][0] and tracker is calls[0][1] for start, tracker in calls))
        self.assertEqual(result['stopRule']['firstSolutionSeconds'],
                         round(calls[0][1].first - calls[0][0], 3))
        self.assertTrue(all(e['code'] in ('coverage', 'sunday_limit', 'night_coverage')
                            for e in validate(raw, result['assignments'])))

    def test_checked_previous_table_is_a_candidate_from_the_start(self):
        self.check_previous_table_without_new_candidate(fixture(3))

    def test_previous_table_can_end_the_first_preference_phase(self):
        self.check_previous_table_without_new_candidate(preference_fixture())

    def check_previous_table_without_new_candidate(self, raw):
        before = solve(raw, seconds=3, allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertIn('assignments', before)
        original = cp_model.CpSolver.solve

        def no_new_table(solver, model, callback=None):
            # 実ソルバーの状態を用意し、その後は候補を出さずに終了監視を待つ。
            limit = solver.parameters.max_time_in_seconds
            solver.parameters.max_time_in_seconds = 0.000001
            original(solver, model)
            solver.parameters.max_time_in_seconds = limit
            deadline = time.monotonic() + limit
            while time.monotonic() < deadline and not stopped.wait(0.02):
                pass
            return cp_model.UNKNOWN

        stopped = threading.Event()
        with patch.object(cp_model.CpSolver, 'solve', no_new_table), \
             patch.object(cp_model.CpSolver, 'stop_search', side_effect=stopped.set):
            result = solve(raw, seconds=10, min_seconds=0.2, after_first=0.1,
                           initial_assignments=before['assignments'],
                           allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertTrue(stopped.is_set())
        self.assertTrue(result['previousKept'])
        self.assertEqual(result['assignments'], before['assignments'])
        self.assertEqual(result['stopRule']['firstSolutionSeconds'], 0)
        self.assertTrue(result['stopRule']['stoppedEarly'])
        self.assertEqual(result['timing']['reason'], 'early_return')


if __name__ == '__main__':
    unittest.main()
