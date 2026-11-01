"""通常版の公休固定：必須条件、追加公休の比較、再改善と独立検査の整合。"""
from copy import deepcopy
import unittest

from solver.engine import solve
from solver.input_data import normalize, overtime_profile
from solver.allocation import metrics
from solver.service import dispatch
from solver.validator import validate, is_rule_exception
from solver.tests.test_night_fairness import six_staff
from solver.tests.test_overtime_fairness import overtime_fixture


def locked_fixture():
    raw, rows = overtime_fixture()
    raw['locked'] = deepcopy(rows)
    raw['fairnessExcludedStaff'] = []
    raw['maxExtraOffSpread'] = 0
    for i, st in enumerate(raw['staff']):
        st['monthlyDaysOff'] = list(rows[st['id']].values()).count('off') - (0 if i == 0 else 3)
    raw['staff'][0]['fixedDaysOff'] = True
    return raw, rows


class FixedDaysOffTests(unittest.TestCase):
    def test_default_and_invalid_flag(self):
        raw = six_staff()
        self.assertTrue(all(not st['fixedDaysOff'] for st in normalize(raw)['staff']))
        for value in (1, 0, 'true', None, []):
            bad = deepcopy(raw)
            bad['staff'][0]['fixedDaysOff'] = value
            self.assertEqual(dispatch({'input': bad})['status'], 'INVALID_INPUT')

    def test_generates_exactly_nine_with_nights_wishes_and_rest_blocks(self):
        raw = six_staff(10)
        raw['requests'] = {'s0': [5, 6]}
        raw['restCountBalance'] = True
        raw['overtimeCycleLimit'] = True
        for st in raw['staff']:
            st.update(fixedDaysOff=True, minConsecutiveRest=1)
        result = solve(raw, seconds=8, quality_first=True, allow_staffing_shortfall=True,
                       allow_rule_exceptions=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(validate(raw, result['assignments']), [])
        self.assertEqual([list(row.values()).count('off') for row in result['assignments'].values()], [9] * 6)
        self.assertEqual(result['assignments']['s0']['5'], 'off')
        self.assertEqual(result['assignments']['s0']['6'], 'off')
        self.assertEqual(set(result['restBalance']['counts']), {st['id'] for st in raw['staff']})
        self.assertEqual(set(result['overtimeFairness']['byStaff']), {st['id'] for st in raw['staff']})

    def test_fixed_does_not_cap_other_staff_extra_holidays_or_change_overtime(self):
        raw, rows = locked_fixture()
        self.assertEqual(validate(raw, rows), [])
        p = normalize(raw)
        metric = metrics(p, rows)
        self.assertEqual((metric['commonExtraDaysOff'], metric['extraOffSpread']), (3, 0))
        old = deepcopy(raw)
        old['staff'][0]['fixedDaysOff'] = False
        self.assertEqual(overtime_profile(p, p['staff'][0]),
                         overtime_profile(normalize(old), normalize(old)['staff'][0]))
        self.assertTrue(any(e['code'] == 'fairness' for e in validate(old, rows)))
        result = solve(raw, seconds=5, quality_first=True, initial_assignments=rows,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(result.get('assignments'), rows, result)
        self.assertEqual(result['fairness']['comparedStaff'], ['s1', 's2', 's3', 's4', 's5'])
        self.assertEqual(result['fairness']['excludedStaff'], ['s0'])
        self.assertEqual(result['allocation']['preservedCommonExtraDaysOff'], 3)
        self.assertIn('s0', result['overtimeFairness']['byStaff'])

    def test_fixed_staff_still_participates_in_overtime_welcome_allocation(self):
        raw, before = overtime_fixture()
        raw['staff'][0].update(fixedDaysOff=True, monthlyDaysOff=25, overtimePreference=2)
        raw['staff'][1]['overtimePreference'] = 2
        result = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(validate(raw, result['assignments']), [])
        self.assertEqual(result['overtimeFairness']['byStaff'], {'s0': 5, 's1': 5, 's2': 3})
        self.assertEqual(list(result['assignments']['s0'].values()).count('off'), 25)
        self.assertEqual(result['allocation']['overtimeTotal'], 13)


    def test_validator_rejects_extra_or_missing_holidays_as_hard_error(self):
        for difference in (-1, 1):
            raw, rows = locked_fixture()
            raw['staff'][0]['monthlyDaysOff'] += difference
            errors = validate(raw, rows)
            error = next(e for e in errors if e['code'] == 'fixed_days_off')
            self.assertEqual(error['actual'], 25)
            self.assertFalse(is_rule_exception(normalize(raw), error))
            self.assertEqual(dispatch({'input': raw, 'action': 'validate', 'assignments': rows})['status'], 'INVALID')
            self.assertEqual(solve(raw, seconds=2, initial_assignments=rows,
                                   allow_staffing_shortfall=True, allow_rule_exceptions=True)['status'], 'INVALID_INPUT')

    def test_too_many_requested_holidays_are_not_silently_accepted(self):
        raw = six_staff()
        raw['staff'][0]['fixedDaysOff'] = True
        raw['requests'] = {'s0': list(range(1, 11))}
        result = solve(raw, seconds=3, allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(result['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', result)

    def test_night_recovery_is_not_counted_as_public_holiday(self):
        raw, rows = locked_fixture()
        st = raw['staff'][3]
        st.update(fixedDaysOff=True, monthlyDaysOff=list(rows['s3'].values()).count('off'))
        result = solve(raw, seconds=3, allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(result.get('assignments'), rows, result)
        st['monthlyDaysOff'] += 1
        self.assertEqual(solve(raw, seconds=3, allow_staffing_shortfall=True,
                               allow_rule_exceptions=True)['status'], 'INFEASIBLE')

    def test_part_time_weekly_limit_is_not_relaxed_to_meet_fixed_quota(self):
        raw = six_staff()
        raw['staff'].append(dict(id='part', type='part', nightShiftType='none', monthlyDaysOff=9,
                                fixedDaysOff=True, maxDaysPerWeek=1, startTime='09:00', endTime='17:00'))
        self.assertEqual(solve(raw, seconds=3, allow_staffing_shortfall=True,
                               allow_rule_exceptions=True)['status'], 'INFEASIBLE')

    def test_conflicting_rest_blocks_do_not_increase_fixed_quota(self):
        raw = six_staff()
        raw['staff'][0].update(fixedDaysOff=True, monthlyDaysOff=1, minConsecutiveRest=1)
        self.assertEqual(solve(raw, seconds=3, allow_staffing_shortfall=True,
                               allow_rule_exceptions=True)['status'], 'INFEASIBLE')


if __name__ == '__main__':
    unittest.main()
