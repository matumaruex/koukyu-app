import unittest
from copy import deepcopy
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_rest import roomy_fixture


class ShortfallDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = roomy_fixture()
        cls.raw.update(requiredStaff=[0, 0, 0], maxReducedSundays=0, dailyRequiredStaff={'5':[0,40,0]})
        cls.raw['requests'] = {'s0':[2,3]}
        cls.raw['locked'] = {'s1':{'4':'night'}}
        cls.result = solve(cls.raw, seconds=10, allow_staffing_shortfall=True)
        assert cls.result['status'] == 'DRAFT', cls.result
        cls.table = cls.result['assignments']

    def test_normal_mode_still_rejects_impossible_staffing(self):
        result = solve(self.raw, seconds=5)
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', result)

    def test_draft_reports_shortfall_with_independent_verification(self):
        errors = validate(self.raw, self.table)
        self.assertEqual(errors, self.result['unmetConditions'])
        self.assertEqual(errors, self.result['validationErrors'])
        self.assertTrue(all(e['code'] == 'coverage' for e in errors))
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['day'], 5)
        self.assertEqual(errors[0]['time'], 600)
        self.assertEqual(errors[0]['required'], 40)
        self.assertLess(errors[0]['actual'], 40)
        self.assertEqual(self.result['staffingShortfallTotal'], 40-errors[0]['actual'])
        self.assertEqual(self.result['verificationScope'], 'DRAFT_WITH_HISTORY')

    def test_draft_keeps_wishes_locked_nights_and_recovery_holidays(self):
        self.assertEqual([self.table['s0'][str(d)] for d in (2,3)], ['off','off'])
        self.assertEqual([self.table['s1'][str(d)] for d in (4,5,6)], ['night','nightOff','off'])
        self.assertLessEqual(self.result['fairness']['spread'], 1)

    def test_draft_does_not_relax_non_staffing_conflicts(self):
        p = deepcopy(self.raw)
        p['locked']['s0'] = {'2':'early'}
        result = solve(p, seconds=5, allow_staffing_shortfall=True)
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', result)
        p = deepcopy(self.raw)
        for st in p['staff']:
            st['nightShiftType'] = 'none'
        result = solve(p, seconds=5, allow_staffing_shortfall=True)
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', result)

    def test_zero_shortfall_is_a_valid_table(self):
        p = roomy_fixture()
        p['requiredStaff'] = [0,0,0]
        r = solve(p, seconds=5, allow_staffing_shortfall=True)
        self.assertIn(r['status'], ('OPTIMAL','FEASIBLE'))
        self.assertEqual(validate(p,r['assignments']), [])
        self.assertEqual(r['validationErrors'], [])

    def test_invalid_draft_flag_and_hard_invalid_initial_comparison_rejected(self):
        for value in (1, None, 'true'):
            self.assertEqual(dispatch({'input':self.raw,'allowStaffingShortfall':value})['status'],'INVALID_INPUT')
        bad = deepcopy(self.table)
        bad['s0']['2'] = 'early'
        self.assertEqual(solve(self.raw, initial_assignments=bad, allow_staffing_shortfall=True)['status'],'INVALID_INPUT')

    def test_verified_draft_can_be_improved_without_worsening_shortfall(self):
        r = solve(self.raw, seconds=3, initial_assignments=self.table, allow_staffing_shortfall=True)
        self.assertEqual(r['status'],'DRAFT')
        self.assertLessEqual(r['staffingShortfallTotal'],self.result['staffingShortfallTotal'])
        # 人数不足→夜勤後希望→夜勤回数差は、残業などの配置評価より上位。
        # 上位が同じときは配置評価も悪化させず、上位が改善する場合も順位全体で比較する。
        def rank(result):
            return (result['staffingShortfallTotal'],
                    len(result['nightRestPreferences']['unmet']),
                    result['allocation']['nightSpread'], result['objective'])
        self.assertLessEqual(rank(r),rank(self.result))
        self.assertGreaterEqual(r['allocation']['commonExtraDaysOff'],self.result['allocation']['commonExtraDaysOff'])
        self.assertTrue(all(e['code']=='coverage' for e in validate(self.raw,r['assignments'])))


if __name__ == '__main__':
    unittest.main()
