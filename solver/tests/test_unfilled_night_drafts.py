"""勤務条件と希望を守り、埋められない夜勤だけを明示した下書き。"""
import unittest
from copy import deepcopy
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_rest import roomy_fixture


class UnfilledNightDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = roomy_fixture()
        cls.raw['requiredStaff'] = [0, 0, 0]
        cls.raw['requests'] = {f's{i}': [6] for i in range(1, 16)}
        cls.raw['shiftRequests'] = {'s0': {'8': 'night'}, 's2': {'4': 'early'}}
        cls.raw['staff'][15].update(dayShiftType='late', nightShiftType='none', canOvertime=False)
        cls.result = solve(cls.raw, seconds=4, allow_staffing_shortfall=True, allow_night_shortfall=True)
        assert cls.result['status'] == 'DRAFT', cls.result

    def test_explicit_opt_in_produces_new_table_and_preserves_hard_conditions(self):
        r = self.result
        self.assertEqual(r['nightShortfallTotal'], 1)
        self.assertEqual(r['daytimeShortfallTotal'], 0)
        self.assertEqual(r['staffingShortfallTotal'], 1)
        self.assertEqual(r['validationErrors'], validate(self.raw, r['assignments']))
        self.assertEqual([(e['code'], e['day'], e['actual'], e['required']) for e in r['validationErrors']], [('night_coverage', 6, 0, 1)])
        self.assertEqual([r['assignments']['s0'][str(d)] for d in (8, 9, 10)], ['night', 'nightOff', 'off'])
        self.assertEqual(r['assignments']['s2']['4'], 'early')
        self.assertTrue(all(k in ('late', 'off', 'nightOff') for k in r['assignments']['s15'].values()))
        for sid in self.raw['requests']:
            self.assertEqual(r['assignments'][sid]['6'], 'off')

    def test_normal_and_existing_daytime_only_draft_still_require_every_night(self):
        for daytime in (False, True):
            r = solve(self.raw, seconds=2, allow_staffing_shortfall=daytime)
            self.assertEqual(r['status'], 'INFEASIBLE')
            self.assertNotIn('assignments', r)

    def test_direct_requests_qualification_and_actual_night_rest_cannot_be_relaxed(self):
        for change in ('double_night', 'ineligible', 'holiday_conflict', 'recovery_conflict'):
            p = deepcopy(self.raw)
            if change == 'double_night':
                p['shiftRequests']['s1'] = {'8': 'night'}
            elif change == 'ineligible':
                p['shiftRequests']['s15'] = {'4': 'early'}
            elif change == 'holiday_conflict':
                p['shiftRequests']['s2']['6'] = 'early'
            else:
                p['shiftRequests']['s0']['10'] = 'early'
            r = solve(p, seconds=2, allow_staffing_shortfall=True, allow_night_shortfall=True)
            self.assertEqual(r['status'], 'INFEASIBLE', change)
            self.assertNotIn('assignments', r)

    def test_night_gap_incumbent_is_accepted_but_excess_nights_are_rejected(self):
        r = solve(self.raw, seconds=2, initial_assignments=self.result['assignments'], allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['status'], 'DRAFT')
        self.assertLessEqual(r['staffingShortfallTotal'], 1)
        bad = deepcopy(self.result['assignments'])
        bad['s3']['8'] = 'night'
        self.assertEqual(solve(self.raw, initial_assignments=bad, allow_staffing_shortfall=True, allow_night_shortfall=True)['status'], 'INVALID_INPUT')

    def test_flag_requires_draft_opt_in_and_strict_boolean(self):
        for value in (1, None, 'true'):
            r = dispatch({'input': self.raw, 'allowStaffingShortfall': True, 'allowNightShortfall': value})
            self.assertEqual(r['status'], 'INVALID_INPUT')
        self.assertEqual(dispatch({'input': self.raw, 'allowNightShortfall': True})['status'], 'INVALID_INPUT')
        self.assertEqual(solve(self.raw, allow_night_shortfall=True)['status'], 'INVALID_INPUT')


if __name__ == '__main__':
    unittest.main()
