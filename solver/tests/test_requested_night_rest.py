"""Selected staff's requested holidays must follow night and recovery.

Contiguous requested holidays are one block. Mandatory rules never soften on timeout
or in a staffing-shortfall draft.
"""
import unittest
from copy import deepcopy
from unittest.mock import patch
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.service import dispatch
from solver.tests.test_night_rest import roomy_fixture


def fixture():
    p = roomy_fixture()
    p['requiredStaff'] = [0, 0, 0]
    p['requests'] = {'s0': [6, 7, 8, 15, 28]}
    p['nightRestRequiredStaff'] = ['s0']
    p['shiftRequests'] = {'s0': {'1': 'early', '2': 'late', '3': 'overtime'}}
    return p


class RequestedNightRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture()
        cls.result = solve(cls.raw, seconds=10, optimize=False)
        assert cls.result['status'] in ('FEASIBLE', 'OPTIMAL'), cls.result

    def test_every_requested_holiday_block_starts_after_night_and_recovery(self):
        a = self.result['assignments']['s0']
        self.assertEqual([a[str(d)] for d in (4, 5, 6, 7, 8)],
                         ['night', 'nightOff', 'off', 'off', 'off'])
        self.assertEqual([a[str(d)] for d in (13, 14, 15)], ['night', 'nightOff', 'off'])
        self.assertEqual([a[str(d)] for d in (26, 27, 28)], ['night', 'nightOff', 'off'])
        self.assertEqual([a[str(d)] for d in (1, 2, 3)], ['early', 'late', 'overtime'])
        self.assertEqual(validate(self.raw, self.result['assignments']), [])

    def test_same_holiday_for_two_selected_staff_is_impossible_even_in_draft(self):
        p = fixture()
        p['requests']['s1'] = [6]
        p['nightRestRequiredStaff'].append('s1')
        for draft in (False, True):
            r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=draft)
            self.assertEqual(r['status'], 'INFEASIBLE')
            self.assertNotIn('assignments', r)

    def test_conflicting_work_requests_and_fixed_shifts_never_override_rule(self):
        for field, shifts in [('shiftRequests', {'4': 'early'}),
                              ('locked', {'5': 'early'})]:
            p = fixture()
            p.setdefault(field, {})['s0'] = shifts
            for draft in (False, True):
                with self.subTest(field=field, draft=draft):
                    r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=draft)
                    self.assertEqual(r['status'], 'INFEASIBLE')
                    self.assertNotIn('assignments', r)

    def test_two_holiday_blocks_too_close_are_impossible(self):
        p = fixture()
        p['requests']['s0'] = [6, 8]
        self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')

    def test_ordinary_requested_holidays_remain_available_for_other_staff(self):
        p = fixture()
        p['requests']['s1'] = [6]
        p['locked'] = {'s1': {'4': 'early', '5': 'late'}}
        r = solve(p, seconds=10, optimize=False)
        self.assertIn(r['status'], ('FEASIBLE', 'OPTIMAL'))
        self.assertEqual([r['assignments']['s1'][str(d)] for d in (4, 5, 6)],
                         ['early', 'late', 'off'])
        self.assertEqual(validate(p, r['assignments']), [])

    def test_period_first_holiday_connects_to_previous_night_and_recovery(self):
        for day, history in [(1, ['off']*5 + ['night', 'nightOff']),
                              (2, ['off']*6 + ['night'])]:
            p = fixture()
            p['shiftRequests'] = {}
            p['requests']['s0'] = list(range(day, day+3))
            p['history']['s0'] = history
            r = solve(p, seconds=10, optimize=False)
            self.assertIn(r['status'], ('FEASIBLE', 'OPTIMAL'))
            self.assertEqual(validate(p, r['assignments']), [])
            for d in range(day, day+3):
                self.assertEqual(r['assignments']['s0'][str(d)], 'off')
        p['history']['s0'] = ['off']*7
        self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')

    def test_impossible_night_qualification_does_not_silently_skip_rule(self):
        p = fixture()
        p['staff'][0]['nightShiftType'] = 'weekday'
        p['requests']['s0'] = [15]  # Required night is day13 (Saturday).
        self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')
        p['staff'][0]['nightShiftType'] = 'none'
        self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')

    def test_independent_validator_detects_chain_even_when_off_date_stays_off(self):
        a = deepcopy(self.result['assignments'])
        # Removing the whole preceding night/recovery pair preserves a normal public holiday.
        a['s0']['4'], a['s0']['5'] = 'early', 'late'
        r = dispatch({'input': self.raw, 'action': 'validate', 'assignments': a})
        self.assertEqual(r['status'], 'INVALID')
        self.assertTrue(any(e['code'] == 'request_night_rest' and e['staff'] == 's0'
                            and e['day'] == 6 for e in r['validationErrors']))
        p = deepcopy(self.raw)
        p['nightRestRequiredStaff'] = []
        self.assertFalse(any(e['code'] == 'request_night_rest' for e in validate(p, a)))

    def test_staffing_shortfall_draft_still_preserves_required_chain(self):
        p = fixture()
        p['dailyRequiredStaff'] = {'20': [0, 40, 0]}
        r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=True)
        self.assertEqual(r['status'], 'DRAFT')
        self.assertEqual([r['assignments']['s0'][str(d)] for d in (4, 5, 6)],
                         ['night', 'nightOff', 'off'])
        self.assertTrue(all(e['code'] == 'coverage' for e in validate(p, r['assignments'])))

    def test_timeout_does_not_soften_night_rest_or_claim_impossibility(self):
        r = solve(fixture(), seconds=0.000001)
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertNotIn('assignments', r)
        with patch('solver.service.solve', return_value={'status': 'UNKNOWN'}) as mocked:
            dispatch({'input': fixture(), 'seconds': 60, 'adaptive': True})
            self.assertEqual(mocked.call_args.args[0]['nightRestRequiredStaff'], ['s0'])

    def test_invalid_selection_and_duplicate_ids_are_rejected(self):
        for value in [True, None, 's0', {}, ['unknown'], ['s0', 's0'], [1]]:
            p = fixture()
            p['nightRestRequiredStaff'] = value
            self.assertEqual(dispatch({'input': p})['status'], 'INVALID_INPUT')
        p = fixture()
        del p['nightRestRequiredStaff']
        self.assertEqual(normalize(p)['nightRestRequiredStaff'], [])


if __name__ == '__main__':
    unittest.main()
