"""残業合計を増やさない公平化、必要な差の証明、時間切れと再開を検証する。"""
import unittest
import time
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
            if not args:
                # ヒント補完は探索段階の最少証明と別の計算。
                return status
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

    def test_fairness_fixes_best_known_total_without_claiming_minimum_total(self):
        raw, before = overtime_fixture()
        # 最後の枠の人数を減らすと合計12回も可能だが、13回の公平化を指定する。
        raw['dailyRequiredStaff']['25'] = [1, 0, 1]
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                  allow_staffing_shortfall=True, allow_rule_exceptions=True,
                  resume={'stage': 'overtime_fairness', 'idle': 0, 'proven': {}})
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['allocation']['overtimeTotal'], 13)
        self.assertEqual(sorted(r['overtimeFairness']['byStaff'].values()), [4, 4, 5])
        self.assertFalse(r['allocation']['minimumOvertimeProven'])
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])
        # 通常の改善は合計削減から始めるので、より少ない合計も引き続き探せる。
        improved = solve(raw, seconds=5, quality_first=True, initial_assignments=r['assignments'],
                         allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(improved['allocation']['overtimeTotal'], 12)

    def test_stalled_unknown_fairness_retries_instead_of_confirming_completion(self):
        raw, before = overtime_fixture()
        real = cp_model.CpSolver.solve

        def unknown_after_stall(solver, model, *args, **kwargs):
            status = real(solver, model, *args, **kwargs)
            if not args:
                # ヒント補完の最適性を、探索の最少証明に流用しないことも確認。
                return status
            # 解探索の再開に失敗し、停滞監視が終了させた状態を再現する。
            time.sleep(.12)
            return cp_model.UNKNOWN

        with patch('solver.quality_search.IDLE_SECONDS',
                   dict.fromkeys(('conditions', 'overtime', 'overtime_fairness', 'placement'), 0)), \
                patch.object(cp_model.CpSolver, 'solve', unknown_after_stall):
            first = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                          allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(first['assignments'], before)
        self.assertFalse(first['search']['done'])
        self.assertTrue(first['search']['continueRecommended'])
        self.assertEqual(first['search']['reason'], 'overtime_fairness_unconfirmed')
        self.assertEqual(first['search']['resume']['stage'], 'overtime_fairness')
        self.assertFalse(first['overtimeFairness']['minimumSpreadProven'])
        second = dispatch({'input': raw, 'seconds': 5, 'qualityFirst': True,
                           'allowStaffingShortfall': True, 'allowRuleExceptions': True,
                           'initialAssignments': before, 'resume': first['search']['resume']})
        self.assertEqual(second['allocation']['overtimeTotal'], 13)
        self.assertEqual(second['overtimeFairness']['spread'], 1)
        self.assertTrue(second['overtimeFairness']['minimumSpreadProven'])

    def test_fixed_total_can_prove_required_spread_without_minimum_total_proof(self):
        raw, before = overtime_fixture()
        raw['shiftRequests'] = {'s0': {str(d): 'overtime' for d in range(1, 12, 2)}}
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                  allow_staffing_shortfall=True, allow_rule_exceptions=True,
                  resume={'stage': 'overtime_fairness', 'idle': 0, 'proven': {}})
        self.assertFalse(r['allocation']['minimumOvertimeProven'])
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(r['overtimeFairness']['spread'], 3)
        self.assertEqual(r['overtimeFairness']['reason'], 'constraints')
        self.assertNotEqual(r['status'], 'OPTIMAL')
        self.assertEqual(r['search']['reason'], 'stalled')

    def test_complete_hints_can_resume_when_shift_only_hints_fail(self):
        raw, before = overtime_fixture()
        real = cp_model.CpSolver.solve

        def requires_complete_hint(solver, model, *args, **kwargs):
            status = real(solver, model, *args, **kwargs)
            if (not solver.parameters.fix_variables_to_their_hinted_value
                    and len(model.proto.solution_hint.vars) < len(model.proto.variables)):
                # 実データで起きた、補助変数の再構築が終わらない状況を再現する。
                return cp_model.UNKNOWN
            return status

        with patch.object(cp_model.CpSolver, 'solve', requires_complete_hint):
            r = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                      allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(r['allocation']['overtimeTotal'], 13)
        self.assertEqual(r['overtimeFairness']['spread'], 1)

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
