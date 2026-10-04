"""A-only/B-only daytime eligibility is hard; night and overtime remain separate."""
import unittest
from copy import deepcopy
from solver.engine import solve, quality_value
from solver.input_data import normalize
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_rest import roomy_fixture


def fixture():
    p = roomy_fixture()
    p['requiredStaff'] = [0, 0, 0]
    p['staff'][0]['dayShiftType'] = 'early'
    p['staff'][1]['dayShiftType'] = 'late'
    p['staff'][3].update(type='fulltime', dayShiftType='early')
    p['shiftRequests'] = {'s0': {'1': 'early', '3': 'overtime'},
                          's1': {'1': 'late', '5': 'overtime', '10': 'night'},
                          's2': {'1': 'early', '2': 'late', '3': 'night'},
                          's3': {'2': 'early'}}
    p['requests'] = {'s0': [6, 7]}
    p['nightRestRequiredStaff'] = ['s0']
    return p


class DayShiftTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture()
        cls.result = solve(cls.raw, seconds=10, optimize=False)
        assert cls.result['status'] in ('FEASIBLE', 'OPTIMAL'), cls.result

    def test_generated_rows_never_contain_forbidden_day_shifts(self):
        a = self.result['assignments']
        self.assertNotIn('late', a['s0'].values())
        self.assertNotIn('early', a['s1'].values())
        self.assertNotIn('late', a['s3'].values())
        self.assertEqual([a['s2'][str(d)] for d in (1, 2)], ['early', 'late'])
        self.assertEqual(validate(self.raw, a), [])

    def test_overtime_nights_and_mandatory_requested_night_rest_remain_available(self):
        a = self.result['assignments']
        self.assertEqual(a['s0']['3'], 'overtime')
        self.assertEqual(a['s1']['5'], 'overtime')
        self.assertEqual(a['s1']['10'], 'night')
        self.assertEqual([a['s0'][str(d)] for d in (4, 5, 6, 7)],
                         ['night', 'nightOff', 'off', 'off'])

    def test_conflicting_requests_and_locked_shifts_are_impossible_including_drafts(self):
        for sid, forbidden in [('s0', 'late'), ('s1', 'early')]:
            for field in ('shiftRequests', 'locked'):
                p = fixture()
                p.setdefault(field, {}).setdefault(sid, {})['20'] = forbidden
                for draft in (False, True):
                    r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=draft)
                    self.assertEqual(r['status'], 'INFEASIBLE')
                    self.assertNotIn('assignments', r)

    def test_independent_validator_catches_wrong_day_shift(self):
        for sid, wrong in [('s0', 'late'), ('s1', 'early')]:
            a = deepcopy(self.result['assignments'])
            a[sid]['1'] = wrong
            r = dispatch({'input': self.raw, 'action': 'validate', 'assignments': a})
            self.assertEqual(r['status'], 'INVALID')
            error = next(e for e in r['validationErrors'] if e['code'] == 'day_shift_eligibility')
            self.assertEqual((error['staff'], error['day'], error['actual']), (sid, 1, wrong))

    def test_past_day_shift_is_not_rewritten_when_current_policy_changes(self):
        p = fixture()
        p['history']['s0'][-1] = 'late'
        self.assertEqual(validate(p, self.result['assignments']), [])

    def test_overtime_cannot_override_its_own_eligibility_setting(self):
        p = fixture()
        p['staff'][0]['canOvertime'] = False
        self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')

    def test_missing_day_shift_type_preserves_legacy_both_mode(self):
        p = fixture()
        for st in p['staff']:
            st.pop('dayShiftType', None)
        self.assertTrue(all(st['dayShiftType'] == 'both' for st in normalize(p)['staff']))
        self.assertEqual(validate(p, self.result['assignments']), [])

    def test_invalid_day_shift_types_are_rejected(self):
        for value in (None, True, 'A', 'B', 'off', [], {}):
            p = fixture()
            p['staff'][0]['dayShiftType'] = value
            self.assertEqual(dispatch({'input': p})['status'], 'INVALID_INPUT')

    def test_day_shift_balance_does_not_reward_unnecessary_overtime_for_a_only(self):
        p = normalize(self.raw)
        a = deepcopy(self.result['assignments'])
        before = quality_value(p, a)
        a['s0']['1'] = 'overtime'
        self.assertEqual(quality_value(p, a) - before, 1)

    def test_staffing_shortfalls_never_relax_day_shift_eligibility(self):
        for mode, needs, expected_shortfall in [('early', [0,0,2], 28), ('late', [2,0,0], 29)]:
            p = roomy_fixture()
            p.update(requiredStaff=needs, maxReducedSundays=0)
            for st in p['staff']:
                st.update(dayShiftType=mode, canOvertime=False)
            self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')
            r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=True)
            self.assertEqual(r['status'], 'DRAFT')
            self.assertEqual(r['staffingShortfallTotal'], expected_shortfall)
            self.assertTrue(all(e['code'] == 'coverage' for e in validate(p, r['assignments'])))
            forbidden = 'late' if mode == 'early' else 'early'
            self.assertTrue(all(forbidden not in row.values() for row in r['assignments'].values()))


if __name__ == '__main__':
    unittest.main()
