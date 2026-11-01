"""夜勤の集中は柔らかく改善し、希望や上位品質は崩さない。すべて架空データ。"""
import unittest
from copy import deepcopy
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.allocation import metrics, weights
from solver.night_distribution import build, report, POLICY, WEIGHT
from solver.quality_search import search
from solver.service import check_resume
from solver.tests.test_overtime_fairness import overtime_fixture


def clustered_fixture():
    nights = [[2, 6, 10, 14, 26], [13, 16, 21, 24, 27, 30],
              [8, 19, 23, 28, 31], [5, 17, 22, 25, 29],
              [3, 9, 12, 15, 18], [1, 4, 7, 11, 20]]
    rows = {f's{i}': {str(d): 'off' for d in range(1, 32)} for i in range(6)}
    for i, days in enumerate(nights):
        for d in days:
            rows[f's{i}'][str(d)] = 'night'
            if d < 31:
                rows[f's{i}'][str(d + 1)] = 'nightOff'
    raw = {'year': 2026, 'month': 10, 'requiredStaff': [0, 0, 0],
           'maxReducedSundays': 0, 'nightDistribution': True,
           'staff': [{'id': f's{i}', 'type': 'full', 'nightShiftType': 'all',
                      'monthlyDaysOff': 0, 'maxConsecutive': 3,
                      'nightRemainderPriority': i == 1} for i in range(6)],
           'fairnessExcludedStaff': list(rows),
           'history': {sid: ['off'] * 7 for sid in rows}}
    return raw, rows


class NightDistributionTests(unittest.TestCase):
    def test_first_half_concentration_is_improved_without_more_overtime_or_shortage(self):
        raw, before = clustered_fixture()
        self.assertEqual(validate(raw, before), [])
        initial = metrics(normalize(raw), before)
        self.assertGreater(initial['nightDistributionPenalty'], 0)
        r = solve(raw, seconds=8, quality_first=True, initial_assignments=before)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'), r)
        self.assertEqual(validate(raw, r['assignments']), [])
        m = r['allocation']
        for field in ('overtimeTotal', 'overtimeBalance', 'surplusTotal', 'nightSpread', 'extraOffSpread'):
            self.assertEqual(m[field], initial[field], field)
        self.assertEqual(m['nightDistributionPenalty'], 0)
        self.assertEqual(r['nightDistribution']['byStaff']['s0']['count'], 5)
        self.assertLessEqual(sum(d <= 15 for d in r['nightDistribution']['byStaff']['s0']['nights']), 3)
        self.assertEqual(r['nightFairness']['byStaff']['s1'], 6)
        self.assertEqual(r['nightDistribution'], report(normalize(raw), r['assignments']))

    def test_requested_cluster_remains_valid_and_is_not_relaxed(self):
        raw, before = clustered_fixture()
        days = [2, 6, 10, 14, 26]
        raw['shiftRequests'] = {'s0': {str(d): 'night' for d in days}}
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'), r)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['nightDistribution']['byStaff']['s0']['nights'], days)
        self.assertGreater(r['nightDistribution']['penalty'], 0)
        self.assertEqual(r['allocation']['overtimeTotal'], 0)

    def test_overtime_total_and_fairness_keep_their_priority(self):
        raw, before = overtime_fixture()
        raw['nightDistribution'] = True
        r = solve(raw, seconds=5, initial_assignments=before)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['allocation']['overtimeTotal'], 13)
        self.assertEqual(sorted(r['overtimeFairness']['byStaff'].values()), [4, 4, 5])
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])

    def test_history_and_fixed_holidays_still_apply(self):
        raw, before = clustered_fixture()
        raw['history']['s1'][-1] = 'night'
        before['s1']['1'] = 'nightOff'
        raw['staff'][0].update(monthlyDaysOff=21, fixedDaysOff=True)
        self.assertEqual(validate(raw, before), [])
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['assignments']['s1']['1'], 'nightOff')
        self.assertEqual(r['assignments']['s1']['2'], 'off')
        self.assertEqual(list(r['assignments']['s0'].values()).count('off'), 21)

    def test_rolling_windows_find_a_cluster_across_the_middle(self):
        raw, rows = clustered_fixture()
        p = normalize(raw)
        for values in ([2, 6, 10, 14, 26], [10, 13, 16, 19, 30]):
            row = {str(d): 'night' if d in values else 'off' for d in range(1, 32)}
            rows['s0'] = row
            scored = report(p, rows)['byStaff']['s0']
            self.assertGreater(scored['windows']['15']['penalty'], 0)
            reversed_rows = deepcopy(rows)
            reversed_rows['s0'] = {str(32 - int(d)): v for d, v in row.items()}
            self.assertEqual(report(p, reversed_rows)['byStaff']['s0']['penalty'], scored['penalty'])
        rows['s0'] = {str(d): 'night' if d in [3, 9, 16, 22, 28] else 'off' for d in range(1, 32)}
        self.assertEqual(report(p, rows)['byStaff']['s0']['penalty'], 0)

    def test_model_and_independent_report_match_in_28_to_31_day_periods(self):
        for year, month in [(2026, 2), (2028, 2), (2026, 9), (2026, 10)]:
            p = normalize({'year': year, 'month': month, 'nightDistribution': True,
                           'staff': [{'id': 's0', 'type': 'full', 'nightShiftType': 'all'}]})
            n = p['days']
            for days in ([], [n], [1, 5, 9, 13, n], [2, 8, 14, 20, 26]):
                model = cp_model.CpModel()
                x = {('s0', d - 1, 'night'): model.new_constant(int(d in days)) for d in range(1, n + 1)}
                total = model.new_constant(len(days))
                expression = build(model, p, x, {'s0': total})
                solver = cp_model.CpSolver()
                self.assertEqual(solver.solve(model), cp_model.OPTIMAL)
                rows = {'s0': {str(d): 'night' if d in days else 'off' for d in range(1, n + 1)}}
                self.assertEqual(solver.value(expression), WEIGHT * report(p, rows)['penalty'])

    def test_old_resume_does_not_reuse_the_old_placement_proof(self):
        raw, before = clustered_fixture()
        old = {'stage': 'placement', 'idle': 600, 'proven': {'placement': True},
               'proofValues': {'placement': [0, 0, 0, 0]}, 'preservedCommonExtraDaysOff': 0}
        with patch('solver.engine.quality_search', wraps=search) as invoked:
            result = solve(raw, seconds=.001, quality_first=True, initial_assignments=before, resume=old)
        passed = invoked.call_args.kwargs['resume']
        self.assertEqual(passed['stage'], 'conditions')
        self.assertEqual(passed['idle'], 0)
        self.assertEqual(passed['proven'], {})
        self.assertEqual(passed['proofValues'], {})
        self.assertEqual(result['search']['resume']['nightDistributionPolicy'], POLICY)
        self.assertEqual(check_resume(result['search']['resume'], True)['nightDistributionPolicy'], POLICY)

    def test_validation_and_weight_bounds(self):
        raw, _ = clustered_fixture()
        for value in (None, 0, 1, 'yes', []):
            raw['nightDistribution'] = value
            with self.assertRaises(ValueError):
                normalize(raw)
        for leave in (0, 12, 18, 22, 30):
            raw = {'year': 2026, 'month': 10, 'nightDistribution': True,
                   'staff': [{'id': f's{i}', 'type': 'full', 'nightShiftType': 'all',
                              'canOvertime': True, 'monthlyDaysOff': 9, 'overtimePreference': i % 3}
                             for i in range(40)],
                   'requests': {f's{i}': list(range(1, leave + 1)) for i in range(0, 40, 2)}}
            self.assertLess(weights(normalize(raw))[1] * 16, 2 ** 63 - 1)

    def test_legacy_api_keeps_the_old_evaluation_without_the_new_flag(self):
        raw, rows = clustered_fixture()
        del raw['nightDistribution']
        p = normalize(raw)
        self.assertEqual(report(p, rows)['penalty'], 0)
        self.assertNotIn('nightDistributionPenalty', metrics(p, rows))


if __name__ == '__main__':
    unittest.main()
