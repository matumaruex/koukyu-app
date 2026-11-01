"""残業を期間内に分散し、合計・歓迎配分・夜勤・希望を守る。すべて架空データ。"""
import unittest
from copy import deepcopy
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.input_data import normalize, overtime_profile
from solver.allocation import metrics, weights
from solver.validator import validate
from solver.overtime_distribution import build, report, score_bound, POLICY, WEIGHT
from solver.quality_search import search
from solver.service import check_resume
from solver.tests.test_overtime_fairness import overtime_fixture


def clustered_overtime_fixture():
    raw, rows = overtime_fixture()
    targets = list(range(1, 26, 2))
    for sid, chosen in zip(('s0', 's1', 's2'), (targets[:4], targets[4:8], targets[8:])):
        for day in targets:
            rows[sid][str(day)] = 'overtime' if day in chosen else 'off'
    raw['staff'][2]['overtimePreference'] = 1
    raw.update(nightDistribution=True, overtimeDistribution=True)
    return raw, rows


def placement_resume():
    return {'stage': 'placement', 'idle': 0, 'proven': {}, 'proofValues': {},
            'preservedCommonExtraDaysOff': 0,
            'nightDistributionPolicy': 'rolling-night-distribution-1',
            'overtimeDistributionPolicy': POLICY}


class OvertimeDistributionTests(unittest.TestCase):
    def test_cluster_improves_without_changing_counts_welcome_or_night_distribution(self):
        raw, before = clustered_overtime_fixture()
        self.assertEqual(validate(raw, before), [])
        initial = metrics(normalize(raw), before)
        self.assertGreater(initial['overtimeDistributionPenalty'], 0)
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before, resume=placement_resume())
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'), r)
        self.assertEqual(validate(raw, r['assignments']), [])
        for field in ('overtimeTotal', 'overtimeBalance', 'overtimeByStaff', 'surplusTotal',
                      'extraOffSpread', 'nightSpread', 'nightDistributionPenalty'):
            self.assertEqual(r['allocation'][field], initial[field], field)
        self.assertEqual(r['allocation']['overtimeByStaff'], {'s0': 4, 's1': 4, 's2': 5})
        self.assertLess(r['allocation']['overtimeDistributionPenalty'], initial['overtimeDistributionPenalty'])
        self.assertLessEqual(sum(d <= 15 for d in r['overtimeDistribution']['byStaff']['s0']['dates']), 3)
        self.assertEqual(r['overtimeDistribution'], report(normalize(raw), r['assignments']))

    def test_requests_are_kept_even_if_they_force_a_cluster(self):
        raw, before = clustered_overtime_fixture()
        raw['shiftRequests'] = {'s0': {str(d): 'overtime' for d in [1, 3, 5, 7]}}
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before, resume=placement_resume())
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['overtimeDistribution']['byStaff']['s0']['dates'], [1, 3, 5, 7])
        self.assertGreater(r['overtimeDistribution']['penalty'], 0)
        self.assertEqual(r['allocation']['overtimeTotal'], 13)

    def test_required_staffing_can_force_a_cluster_without_invalidating_the_table(self):
        raw, before = clustered_overtime_fixture()
        raw['locked'] = deepcopy(before)
        r = solve(raw, seconds=2, quality_first=True, initial_assignments=before, resume=placement_resume())
        self.assertEqual(r['assignments'], before)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertGreater(r['overtimeDistribution']['penalty'], 0)
        self.assertNotEqual(r['status'], 'INFEASIBLE')

    def test_proportional_cap_and_long_leave_still_apply(self):
        raw, before = clustered_overtime_fixture()
        raw['staff'][0]['monthlyDaysOff'] = 9
        raw['requests'] = {'s0': list(range(15, 32))}
        raw['shiftRequests'] = {'s0': {str(d): 'overtime' for d in [1, 3, 5, 7]}}
        p = normalize(raw)
        self.assertEqual(overtime_profile(p, p['staff'][0])['cap'], 4)
        self.assertEqual(validate(raw, before), [])
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before, resume=placement_resume())
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['overtimeDistribution']['byStaff']['s0']['dates'], [1, 3, 5, 7])
        self.assertTrue(all(r['assignments']['s0'][str(d)] == 'off' for d in range(15, 32)))

    def test_rolling_intervals_detect_clusters_on_either_side_of_the_middle(self):
        raw, rows = clustered_overtime_fixture()
        p = normalize(raw)
        for dates in ([1, 3, 5, 7], [11, 13, 15, 17]):
            rows['s0'] = {str(d): 'overtime' if d in dates else 'off' for d in range(1, 32)}
            scored = report(p, rows)['byStaff']['s0']
            self.assertGreater(scored['penalty'], 0)
            reversed_rows = deepcopy(rows)
            reversed_rows['s0'] = {str(32 - int(d)): shift for d, shift in rows['s0'].items()}
            self.assertEqual(report(p, reversed_rows)['byStaff']['s0']['penalty'], scored['penalty'])
        rows['s0'] = {str(d): 'overtime' if d in [3, 11, 19, 27] else 'off' for d in range(1, 32)}
        self.assertEqual(report(p, rows)['byStaff']['s0']['penalty'], 0)

    def test_model_report_and_bounds_allow_multiple_staff_overtime_on_the_same_day(self):
        for year, month in [(2026, 2), (2028, 2), (2026, 9), (2026, 10)]:
            p = normalize({'year': year, 'month': month, 'overtimeDistribution': True,
                           'staff': [{'id': sid, 'type': 'full', 'canOvertime': True} for sid in ('a', 'b')]})
            n = p['days']
            for dates in ([], [n], [1, 3, 5, 7], [1, 3, 5, 7, 9, 11], [3, 11, 19, 27]):
                model = cp_model.CpModel()
                x = {(sid, day - 1, 'overtime'): model.new_constant(int(day in dates))
                     for sid in ('a', 'b') for day in range(1, n + 1)}
                totals = {sid: model.new_constant(len(dates)) for sid in ('a', 'b')}
                expression = build(model, p, x, totals)
                solver = cp_model.CpSolver()
                self.assertEqual(solver.solve(model), cp_model.OPTIMAL)
                rows = {sid: {str(d): 'overtime' if d in dates else 'off' for d in range(1, n + 1)} for sid in ('a', 'b')}
                score = report(p, rows)['penalty']
                self.assertLessEqual(score, score_bound(p))
                self.assertEqual(solver.value(expression), WEIGHT * score)

    def test_old_resume_is_restarted_and_new_resume_round_trips(self):
        raw, before = clustered_overtime_fixture()
        old = placement_resume()
        del old['overtimeDistributionPolicy']
        old.update(idle=600, proven={'placement': True}, proofValues={'placement': [0, 0, 0, 0]})
        with patch('solver.engine.quality_search', wraps=search) as invoked:
            r = solve(raw, seconds=.001, quality_first=True, initial_assignments=before, resume=old)
        passed = invoked.call_args.kwargs['resume']
        self.assertEqual(passed['stage'], 'conditions')
        self.assertEqual(passed['idle'], 0)
        self.assertEqual(passed['proven'], {})
        self.assertEqual(r['search']['resume']['overtimeDistributionPolicy'], POLICY)
        self.assertEqual(check_resume(r['search']['resume'], True)['overtimeDistributionPolicy'], POLICY)
        with self.assertRaises(ValueError):
            check_resume(dict(placement_resume(), overtimeDistributionPolicy=42), True)

    def test_boolean_validation_and_old_api_compatibility(self):
        raw, before = clustered_overtime_fixture()
        for value in (None, 0, 1, 'yes', []):
            with self.assertRaises(ValueError):
                normalize(dict(raw, overtimeDistribution=value))
        del raw['overtimeDistribution']
        self.assertEqual(report(normalize(raw), before)['penalty'], 0)
        self.assertNotIn('overtimeDistributionPenalty', metrics(normalize(raw), before))

    def test_combined_weights_remain_safe_with_forty_staff_and_proportional_preferences(self):
        for leave in (0, 12, 18, 22, 30):
            raw = {'year': 2026, 'month': 10, 'nightDistribution': True, 'overtimeDistribution': True,
                   'staff': [{'id': f's{i}', 'type': 'full', 'nightShiftType': 'all', 'canOvertime': True,
                              'monthlyDaysOff': 9, 'overtimePreference': i % 3} for i in range(40)],
                   'requests': {f's{i}': list(range(1, leave + 1)) for i in range(0, 40, 2)}}
            self.assertLess(weights(normalize(raw))[1] * 16, 2 ** 63 - 1)


if __name__ == '__main__':
    unittest.main()
