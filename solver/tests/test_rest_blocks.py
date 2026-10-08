"""連休は別々の公休のまとまり。完成表・手直し・おまかせで必須を破らない。"""
from copy import deepcopy
import unittest

from solver.engine import solve
from solver.input_data import normalize
from solver.rest_blocks import ranges
from solver.service import dispatch
from solver.validator import validate, is_rule_exception
from solver.auto_schedule import inspect
from solver.tests.test_overtime_fairness import overtime_fixture
from solver.tests.test_auto_schedule import policy_for, reduction_fixture


def fixed_day_fixture(two=False):
    raw, rows = overtime_fixture()
    raw['dailyRequiredStaff'] = {}
    raw['staff'][0].update(canOvertime=False, minConsecutiveRest=2 if two else 1)
    shifts = ['off'] * 4 + ['early']
    if two:
        shifts += ['off', 'off', 'early']
    while len(shifts) < 31:
        shifts.append('off' if shifts[-1] == 'early' else 'early')
    rows['s0'] = {str(d): shift for d, shift in enumerate(shifts, 1)}
    raw['locked'] = deepcopy(rows)
    return raw, rows


class RestBlockTests(unittest.TestCase):
    def test_two_days_or_four_days_are_one_block_and_separated_is_two(self):
        for length in (2, 3, 4):
            self.assertEqual(ranges(dict(enumerate(['off'] * length, 1)), 31),
                             [{'start': 1, 'end': length}])
        self.assertEqual(ranges({'1': 'off', '2': 'off', '3': 'early', '4': 'off', '5': 'off'}, 31),
                         [{'start': 1, 'end': 2}, {'start': 4, 'end': 5}])

    def test_night_off_is_not_a_holiday_and_missing_cells_split_blocks(self):
        self.assertEqual(ranges({'1': 'nightOff', '2': 'off'}, 31), [])
        self.assertEqual(ranges({'1': 'nightOff', '2': 'off', '3': 'off'}, 31), [{'start': 2, 'end': 3}])
        self.assertEqual(ranges({'1': 'off', '3': 'off'}, 31), [])

    def test_period_boundary_clips_blocks_in_all_month_lengths(self):
        for n in (28, 29, 30, 31):
            row = {'0': 'off', '1': 'off', str(n): 'off', str(n + 1): 'off'}
            self.assertEqual(ranges(row, n), [])
            row['2'] = row[str(n - 1)] = 'off'
            self.assertEqual(ranges(row, n), [{'start': 1, 'end': 2}, {'start': n - 1, 'end': n}])

    def test_old_input_defaults_to_disabled_and_invalid_values_are_rejected(self):
        raw, _ = overtime_fixture()
        self.assertTrue(all(st['minConsecutiveRest'] == 0 for st in normalize(raw)['staff']))
        for value in (-1, 3, True, '1', None, 1.0):
            bad = deepcopy(raw)
            bad['staff'][0]['minConsecutiveRest'] = value
            self.assertEqual(dispatch({'input': bad})['status'], 'INVALID_INPUT')

    def test_explicit_zero_has_same_assignments_and_quality_as_omitted_setting(self):
        raw, rows = fixed_day_fixture()
        del raw['staff'][0]['minConsecutiveRest']
        zero = deepcopy(raw)
        for st in zero['staff']:
            st['minConsecutiveRest'] = 0
        old = solve(raw, seconds=5, quality_first=True, allow_staffing_shortfall=True,
                    allow_rule_exceptions=True)
        new = solve(zero, seconds=5, quality_first=True, allow_staffing_shortfall=True,
                    allow_rule_exceptions=True)
        self.assertEqual(new['assignments'], rows)
        self.assertEqual(new['allocation'], old['allocation'])
        self.assertNotIn('consecutiveRest', new)

    def test_normal_solver_preserves_requested_rest_and_counts_long_block_once(self):
        raw, rows = fixed_day_fixture()
        raw['requests'] = {'s0': [1, 2, 3, 4]}
        result = solve(raw, seconds=5, quality_first=True, allow_staffing_shortfall=True,
                       allow_rule_exceptions=True)
        self.assertIn(result['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(result['assignments'], rows)
        self.assertEqual(result['consecutiveRest']['s0'],
                         {'required': 1, 'actual': 1, 'ranges': [{'start': 1, 'end': 4}]})
        self.assertEqual(validate(raw, result['assignments']), [])

    def test_required_two_needs_two_separate_blocks(self):
        raw, rows = fixed_day_fixture(two=True)
        result = solve(raw, seconds=5, allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertIn('assignments', result)
        self.assertEqual(result['consecutiveRest']['s0']['actual'], 2)
        raw['locked']['s0']['5'] = 'off'
        self.assertEqual(solve(raw, seconds=5, allow_staffing_shortfall=True,
                               allow_rule_exceptions=True)['status'], 'INFEASIBLE')

    def test_free_solver_creates_required_blocks_instead_of_overlapping_pairs(self):
        raw, rows = fixed_day_fixture()
        raw['staff'][0]['minConsecutiveRest'] = 2
        del raw['locked']['s0']
        raw['requests'] = {'s0': [1, 2, 3, 4]}
        result = solve(raw, seconds=5, quality_first=True, allow_staffing_shortfall=True,
                       allow_rule_exceptions=True)
        self.assertIn('assignments', result)
        self.assertEqual(validate(raw, result['assignments']), [])
        self.assertGreaterEqual(len(ranges(result['assignments']['s0'], 31)), 2)
        self.assertTrue(all(result['assignments']['s0'][str(d)] == 'off' for d in (1, 2, 3, 4)))

    def test_edit_validation_reports_hard_shortfall_without_allowed_exception(self):
        raw, rows = fixed_day_fixture()
        raw['staff'][0]['minConsecutiveRest'] = 2
        result = dispatch({'input': raw, 'action': 'validate', 'assignments': rows})
        self.assertEqual(result['status'], 'INVALID')
        error = next(e for e in result['validationErrors'] if e['code'] == 'rest_blocks')
        self.assertEqual((error['actual'], error['required']), (1, 2))
        self.assertFalse(is_rule_exception(normalize(raw), error))
        self.assertEqual(result['consecutiveRest']['s0']['actual'], 1)
        with self.assertRaises(ValueError):
            inspect(raw, rows)

    def test_diagnosis_keeps_wishes_and_explains_rest_shortfall_without_adopting_table(self):
        raw, _ = fixed_day_fixture()
        del raw['locked']['s0']
        raw['staff'][0]['minConsecutiveRest'] = 2
        raw['requests'] = {'s0': list(range(1, 32))}
        result = dispatch({'input': raw, 'seconds': 5, 'qualityFirst': True,
                           'allowStaffingShortfall': True, 'allowRuleExceptions': True})
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', result)
        diagnostic = result['diagnosis']
        self.assertTrue(diagnostic['proven'])
        self.assertEqual(diagnostic['droppedWishes'], [])
        self.assertEqual(diagnostic['restShortfalls'], [{'staff': 's0', 'required': 2, 'actual': 1, 'missing': 1}])
        self.assertNotIn('assignments', diagnostic)

    def test_auto_base_adjust_and_finish_keep_required_blocks(self):
        raw, rows = fixed_day_fixture(two=True)
        policy = policy_for(raw)
        base = dict(mode='auto', input=raw, holidayPolicy=policy, seconds=5)
        result = dispatch(dict(base, autoPhase='base'))
        self.assertIn('assignments', result)
        adjusted = dispatch(dict(base, autoPhase='adjust', referenceAssignments=result['assignments']))
        self.assertIn('assignments', adjusted)
        finished = dispatch(dict(base, autoPhase='finish', initialAssignments=adjusted['assignments'],
                                 selectedQuota=adjusted['selectedQuota']))
        self.assertIn('assignments', finished)
        for item in (result, adjusted, finished):
            self.assertEqual(item['consecutiveRest']['s0']['actual'], 2)
            self.assertEqual(item['assignments']['s0'], rows['s0'])

    def test_auto_cannot_relax_rest_even_when_holiday_count_can_be_reduced(self):
        raw, _, policy = reduction_fixture(locked=True)
        raw['staff'][-1]['minConsecutiveRest'] = 2
        result = dispatch(dict(mode='auto', autoPhase='adjust', input=raw, holidayPolicy=policy, seconds=5))
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', result)

    def test_part_time_staff_also_get_two_blocks_and_keep_weekly_limits(self):
        raw, rows, _ = reduction_fixture()
        raw['staff'][-1].update(monthlyDaysOff=25, minConsecutiveRest=2)
        rows['p'] = {str(d): 'part' if d <= 5 or d == 8 else 'off' for d in range(1, 32)}
        raw['locked']['p'] = deepcopy(rows['p'])
        for mode in ('normal', 'auto'):
            payload = dict(input=raw, seconds=5, qualityFirst=True, allowStaffingShortfall=True,
                           allowRuleExceptions=True)
            if mode == 'auto':
                payload.update(mode='auto', autoPhase='base', holidayPolicy=policy_for(raw))
            result = dispatch(payload)
            self.assertIn('assignments', result)
            self.assertEqual(validate(raw, result['assignments']), [])
            self.assertEqual(result['consecutiveRest']['p'],
                             {'required': 2, 'actual': 2,
                              'ranges': [{'start': 6, 'end': 7}, {'start': 9, 'end': 31}]})


if __name__ == '__main__':
    unittest.main()
