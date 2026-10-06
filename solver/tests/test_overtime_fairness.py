"""残業合計を増やさない公平化、必要な差の証明、時間切れと再開を検証する。"""
import unittest
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_fairness import six_staff

from copy import deepcopy

def overtime_fixture():
    n = 31
    targets = list(range(1, 26, 2))
    rows = {f's{i}': {str(d): 'off' for d in range(1, n + 1)} for i in range(6)}
    history = {sid: ['off'] * 7 for sid in rows}
    history['s5'][-1] = 'night'
    for d in range(1, n + 1):
        rows[f's{3 + (d - 1) % 3}'][str(d)] = 'night'
        rows[f's{3 + (d - 2) % 3}'][str(d)] = 'nightOff'
    for sid, slots in zip(('s0', 's1', 's2'), (targets[:6], targets[6:10], targets[10:])):
        for d in slots:
            rows[sid][str(d)] = 'overtime'
    raw = {'year': 2026, 'month': 10,
           'staff': [{'id': f's{i}', 'type': 'full', 'monthlyDaysOff': 0,
                      'nightShiftType': 'none' if i < 3 else 'all',
                      'dayShiftType': 'early' if i < 3 else 'both',
                      'canOvertime': i < 3, 'maxConsecutive': 3} for i in range(6)],
           'history': history, 'fairnessExcludedStaff': list(rows),
           'requiredStaff': [0, 0, 0], 'maxReducedSundays': 0,
           'dailyRequiredStaff': {str(d): [2, 1, 2] for d in targets},
           'locked': deepcopy(rows)}
    for sid in ('s0', 's1', 's2'):
        for d in targets:
            del raw['locked'][sid][str(d)]
    return raw, rows

class OvertimeFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.before = overtime_fixture()
        cls.result = solve(cls.raw, seconds=5, quality_first=True,
                           initial_assignments=cls.before, allow_staffing_shortfall=True,
                           allow_rule_exceptions=True)

    def test_six_four_three_is_rebalanced_without_more_overtime(self):
        self.assertEqual(validate(self.raw, self.before), [])
        r = self.result
        self.assertEqual(validate(self.raw, r['assignments']), [])
        self.assertEqual(r['allocation']['overtimeTotal'], 13)
        self.assertEqual(sorted(r['overtimeFairness']['byStaff'].values()), [4, 4, 5])
        self.assertEqual(r['overtimeFairness']['spread'], 1)
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(r['overtimeFairness']['reason'], 'balanced')
        self.assertTrue(r['allocation']['minimumOvertimeProven'])
        self.assertIn('overtime_fairness', [s['stage'] for s in r['search']['stages']])
        self.assertNotIn('s3', r['overtimeFairness']['byStaff'])

    def test_wishes_can_require_a_larger_proven_minimum_spread(self):
        raw, before = overtime_fixture()
        raw['shiftRequests'] = {'s0': {str(d): 'overtime' for d in range(1, 12, 2)}}
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                  allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['allocation']['overtimeTotal'], 13)
        self.assertEqual(sorted(r['overtimeFairness']['byStaff'].values()), [3, 4, 6])
        self.assertEqual(r['overtimeFairness']['idealSpread'], 1)
        self.assertEqual(r['overtimeFairness']['spread'], 3)
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(r['overtimeFairness']['reason'], 'constraints')

    def test_unconfirmed_fairness_is_not_called_unavoidable_and_can_resume(self):
        raw, before = overtime_fixture()
        raw['shiftRequests'] = {'s0': {str(d): 'overtime' for d in range(1, 12, 2)}}
        real = cp_model.CpSolver.solve
        calls = []
        def incomplete(solver, model, *args, **kwargs):
            status = real(solver, model, *args, **kwargs)
            calls.append(status)
            return cp_model.FEASIBLE if len(calls) == 3 and status == cp_model.OPTIMAL else status
        with patch.object(cp_model.CpSolver, 'solve', incomplete):
            first = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                          allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertFalse(first['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(first['overtimeFairness']['reason'], 'not_proven')
        self.assertEqual(first['search']['resume']['stage'], 'overtime_fairness')
        second = dispatch({'input': raw, 'seconds': 5, 'qualityFirst': True,
                           'allowStaffingShortfall': True, 'allowRuleExceptions': True,
                           'initialAssignments': first['assignments'], 'resume': first['search']['resume']})
        self.assertEqual(second['search']['stages'][0]['stage'], 'overtime_fairness')
        self.assertLessEqual(second['allocation']['overtimeTotal'], first['allocation']['overtimeTotal'])
        self.assertTrue(second['overtimeFairness']['minimumSpreadProven'])

    def test_timeout_keeps_the_checked_table_without_false_proof(self):
        r = solve(self.raw, seconds=0.000001, quality_first=True,
                  initial_assignments=self.before, allow_staffing_shortfall=True,
                  allow_rule_exceptions=True)
        self.assertEqual(r['assignments'], self.before)
        self.assertFalse(r['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(r['overtimeFairness']['reason'], 'not_proven')

    def test_no_eligible_staff_has_no_overtime_comparison(self):
        raw = six_staff()
        for st in raw['staff']:
            st['canOvertime'] = False
        r = solve(raw, seconds=5, quality_first=True)
        self.assertEqual(r['overtimeFairness']['byStaff'], {})
        self.assertEqual(r['overtimeFairness']['spread'], 0)
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])
        self.assertNotIn('overtime_fairness', [s['stage'] for s in r['search']['stages']])

if __name__ == '__main__':
    unittest.main()
