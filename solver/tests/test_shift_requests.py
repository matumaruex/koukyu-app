"""Exact shift wishes are mandatory, including in staffing-shortfall drafts."""
import unittest
from copy import deepcopy
from solver.input_data import normalize
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_rest import roomy_fixture


def requested_fixture():
    p = roomy_fixture()
    p['requiredStaff'] = [0, 0, 0]
    p['shiftRequests'] = {'s0': {'1': 'early', '2': 'late', '3': 'overtime',
                               '6': 'night', '28': 'night'}, 's1': {'27': 'night'}}
    p['requests'] = {'s0': [10]}
    return p


class ShiftRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = requested_fixture()
        cls.result = solve(cls.raw, seconds=10, optimize=False)
        assert cls.result['status'] in ('OPTIMAL', 'FEASIBLE'), cls.result

    def test_all_requested_shifts_and_off_days_are_exact(self):
        table = self.result['assignments']
        for sid, wishes in self.raw['shiftRequests'].items():
            for day, shift in wishes.items():
                self.assertEqual(table[sid][day], shift)
        self.assertEqual(table['s0']['10'], 'off')
        self.assertEqual(validate(self.raw, table), [])

    def test_requested_night_preserves_recovery_and_boundary_carry(self):
        self.assertEqual([self.result['assignments']['s0'][str(d)] for d in (6,7,8)],
                         ['night', 'nightOff', 'off'])
        self.assertEqual(self.result['carryForward']['s0']['nextDays'], ['nightOff', 'off'])
        self.assertEqual(self.result['carryForward']['s1']['nextDays'], ['off'])

    def test_independent_validator_detects_changed_work_and_night(self):
        for day, changed in [('1', 'late'), ('6', 'early')]:
            table = deepcopy(self.result['assignments'])
            table['s0'][day] = changed
            r = dispatch({'action': 'validate', 'input': self.raw, 'assignments': table})
            self.assertEqual(r['status'], 'INVALID')
            error = next(e for e in r['validationErrors'] if e['code'] == 'shift_request')
            self.assertEqual((error['staff'], error['day'], error['requested'], error['actual']),
                             ('s0', int(day), self.raw['shiftRequests']['s0'][day], changed))

    def test_contradictory_requests_are_impossible_even_in_drafts(self):
        for changes in [
            {'requests': {'s0': [1]}},
            {'locked': {'s0': {'1': 'late'}}},
            {'shiftRequests': {'s0': {'6': 'night', '7': 'early'}}},
            {'shiftRequests': {'s0': {'6': 'night', '8': 'late'}}},
            {'shiftRequests': {'s0': {'6': 'night'}, 's1': {'6': 'night'}}},
            {'shiftRequests': {'s0': {'1': 'overtime', '2': 'overtime'}}},
            {'history': {'s0': ['off']*5 + ['night', 'nightOff']},
             'shiftRequests': {'s0': {'1': 'early'}}},
            {'history': {'s0': ['off']*6 + ['night']},
             'shiftRequests': {'s0': {'1': 'late'}}},
        ]:
            p = requested_fixture()
            p.update(changes)
            for draft in (False, True):
                with self.subTest(changes=changes, draft=draft):
                    r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=draft)
                    self.assertEqual(r['status'], 'INFEASIBLE')
                    self.assertNotIn('assignments', r)

    def test_eligibility_cannot_be_overridden_by_a_wish(self):
        for config, wish in [({'nightShiftType': 'none'}, 'night'),
                             ({'canOvertime': False}, 'overtime'),
                             ({'nightShiftType': 'weekday'}, 'night'),
                             ({}, 'part')]:
            p = requested_fixture()
            p['staff'][0].update(config)
            # Period day 5 is Friday: weekday-only night work cannot be requested.
            p['shiftRequests'] = {'s0': {'5': wish}}
            self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')

    def test_part_time_requested_work_obeys_configured_hours_and_limits(self):
        p = requested_fixture()
        p['staff'].append({'id': 'p', 'type': 'part', 'monthlyDaysOff': 12,
                           'nightShiftType': 'none', 'maxDaysPerWeek': 5,
                           'startTime': '09:00', 'endTime': '16:00'})
        p['history']['p'] = ['off'] * 7
        p['shiftRequests']['p'] = {'3': 'part', '5': 'part'}
        r = solve(p, seconds=10, optimize=False)
        self.assertIn(r['status'], ('FEASIBLE', 'OPTIMAL'))
        self.assertEqual([r['assignments']['p'][d] for d in ('3', '5')], ['part', 'part'])
        self.assertEqual(validate(p, r['assignments']), [])
        p['shiftRequests']['p'] = {'3': 'early'}
        self.assertEqual(solve(p, seconds=5, optimize=False)['status'], 'INFEASIBLE')

    def test_staffing_shortfall_draft_keeps_every_requested_shift(self):
        p = requested_fixture()
        p['dailyRequiredStaff'] = {'12': [0, 40, 0]}
        r = solve(p, seconds=5, optimize=False, allow_staffing_shortfall=True)
        self.assertEqual(r['status'], 'DRAFT')
        for sid, wishes in p['shiftRequests'].items():
            for day, shift in wishes.items():
                self.assertEqual(r['assignments'][sid][day], shift)
        self.assertTrue(all(e['code'] == 'coverage' for e in validate(p, r['assignments'])))

    def test_invalid_request_shapes_days_shifts_and_staff_are_rejected(self):
        for wishes in [[], None, {'missing': {'1': 'early'}}, {'s0': []},
                       {'s0': {'0': 'early'}}, {'s0': {'29': 'night'}},
                       {'s0': {True: 'early'}}, {'s0': {'1': 'off'}},
                       {'s0': {'1': 'nightOff'}}, {'s0': {'1': []}},
                       {'s0': {'1': 'early', '01': 'late'}}]:
            p = requested_fixture()
            p['shiftRequests'] = wishes
            with self.subTest(wishes=wishes):
                self.assertEqual(dispatch({'input': p})['status'], 'INVALID_INPUT')

    def test_old_inputs_and_empty_requests_keep_same_behavior(self):
        p = roomy_fixture()
        p['requiredStaff'] = [0, 0, 0]
        self.assertEqual(normalize(p)['shiftRequests'], {})
        p['shiftRequests'] = {}
        self.assertEqual(validate(p, self.result['assignments']), [])


if __name__ == '__main__':
    unittest.main()
