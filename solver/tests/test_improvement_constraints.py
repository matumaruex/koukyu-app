"""改善の開始時に守った追加公休と、その範囲の証明を通信の続きでも維持する。"""
import unittest
from copy import deepcopy
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.quality_search import search
from solver.service import check_resume, dispatch
from solver.tests.test_monthly_allocation import exchange_fixture
from solver.validator import validate


class ImprovementConstraintsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw, before = exchange_fixture()
        for staff in raw['staff']:
            staff['monthlyDaysOff'] -= 1
        raw['maxExtraOffSpread'] = 1
        raw['staff'][1].update(canOvertime=True, overtimePreference=1)
        raw['locked'] = deepcopy(before)
        for sid in ('s0', 's1'):
            raw['locked'][sid].pop('4')
        cls.raw, cls.before = raw, before
        cls.options = dict(seconds=5, quality_first=True, allow_staffing_shortfall=True,
                           allow_rule_exceptions=True)

        def interrupted(*args, **kwargs):
            # 最初の3段階は実CP-SATで証明する。配置段階の通信切れを再現する。
            result = search(*args, **kwargs)
            assert result['priorityProven'] and result['overtimeProven'] and result['overtimeSpreadProven']
            p = result['priorityValue']
            result['status'] = cp_model.FEASIBLE
            result['info'].update(done=False, continueRecommended=True, reason='placement_unconfirmed',
                                  resume={'stage': 'placement', 'idle': 0,
                                          'proven': {'conditions': True, 'overtime': True, 'overtime_fairness': True},
                                          'proofValues': {'conditions': [p], 'overtime': [p, 1],
                                                          'overtime_fairness': [p, 1, 2]}})
            return result

        with patch('solver.engine.quality_search', interrupted):
            cls.first = solve(raw, initial_assignments=before, **cls.options)

    def test_continuation_keeps_original_extra_holidays_and_proof_scope(self):
        first = self.first
        self.assertEqual(first['allocation']['commonExtraDaysOff'], 1)
        result = dispatch({'input': self.raw, 'seconds': 5, 'qualityFirst': True,
                           'allowStaffingShortfall': True, 'allowRuleExceptions': True,
                           'initialAssignments': first['assignments'], 'resume': first['search']['resume']})
        self.assertEqual(validate(self.raw, result['assignments']), [])
        self.assertEqual(result['allocation']['commonExtraDaysOff'], 1)
        self.assertEqual(result['allocation']['preservedCommonExtraDaysOff'], 1)
        self.assertEqual(result['allocation']['overtimeTotal'], 1)
        self.assertEqual(result['allocation']['overtimeBalance'], 2)
        self.assertTrue(result['allocation']['minimumOvertimeProven'])

    def test_new_creation_continuation_does_not_freeze_temporary_extra_holidays(self):
        result = solve(self.raw, initial_assignments=self.first['assignments'],
                       resume={'stage': 'conditions', 'idle': 0, 'proven': {}, 'proofValues': {},
                               'preservedCommonExtraDaysOff': None}, **self.options)
        self.assertEqual(result['allocation']['overtimeTotal'], 0)
        self.assertEqual(result['allocation']['commonExtraDaysOff'], 0)
        self.assertIsNone(result['allocation']['preservedCommonExtraDaysOff'])
        self.assertEqual(validate(self.raw, result['assignments']), [])

    def test_old_continuation_without_constraint_scope_does_not_reuse_proof(self):
        resume = deepcopy(self.first['search']['resume'])
        resume.pop('preservedCommonExtraDaysOff', None)
        result = solve(self.raw, initial_assignments=self.first['assignments'], resume=resume, **self.options)
        self.assertFalse(result['allocation']['minimumOvertimeProven'])
        self.assertFalse(result['preferencePriorityProven'])

    def test_constraint_scope_input_checks(self):
        resume = dict(stage='placement', idle=0, proven={}, preservedCommonExtraDaysOff=1)
        self.assertEqual(check_resume(resume, True)['preservedCommonExtraDaysOff'], 1)
        self.assertIsNone(check_resume(dict(resume, preservedCommonExtraDaysOff=None), True)['preservedCommonExtraDaysOff'])
        for bad in (-1, 32, True, 1.5, '1'):
            with self.assertRaises(ValueError):
                check_resume(dict(resume, preservedCommonExtraDaysOff=bad), True)
        result = solve(self.raw, initial_assignments=self.before,
                       resume=dict(resume, preservedCommonExtraDaysOff=2), **self.options)
        self.assertEqual(result['status'], 'INVALID_INPUT')


if __name__ == '__main__':
    unittest.main()
