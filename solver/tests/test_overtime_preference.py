"""歓迎への配分、合計優先、比率と絶対上限、証明、おまかせとの分離を検査する。"""
import itertools
import unittest
from copy import deepcopy
from unittest.mock import patch
from solver.allocation import metrics, weights, overtime_scales
from solver.overtime_preference import minimum_balance, offsets
from solver.input_data import normalize
from solver.engine import solve
from solver.auto_schedule import inspect, HolidayPlan
from solver.holiday_policy import checked_policy
from solver.validator import validate
from solver.tests.test_overtime_fairness import overtime_fixture
from solver.tests.test_proportional_overtime import leave_fixture


def six_overtime_fixture():
    raw, _ = overtime_fixture()
    targets = list(range(1, 22, 2))
    rows = deepcopy(raw['locked'])
    for sid in ('s0', 's1', 's2'):
        rows[sid] = {str(d): 'off' for d in range(1, 32)}
    for i in range(3):
        st = dict(raw['staff'][i], id=f'd{i}')
        raw['staff'].append(st)
        rows[st['id']] = {str(d): 'off' for d in range(1, 32)}
        raw['history'][st['id']] = ['off'] * 7
    raw['fairnessExcludedStaff'] = list(rows)
    raw['locked'] = rows
    raw['dailyRequiredStaff'] = {str(d): [3, 2, 3] for d in targets}
    for st in raw['staff']:
        if st['canOvertime']:
            for d in targets:
                del raw['locked'][st['id']][str(d)]
    return raw


def run(raw, **kw):
    return solve(raw, seconds=10, quality_first=True, allow_staffing_shortfall=True,
                 allow_rule_exceptions=True, **kw)


class PreferenceTests(unittest.TestCase):
    def test_two_welcome_staff_get_five_others_three_with_same_total(self):
        raw = six_overtime_fixture()
        raw['staff'][0]['overtimePreference'] = 2
        raw['staff'][1]['overtimePreference'] = 2
        result = run(raw)
        self.assertEqual(validate(raw, result['assignments']), [])
        f = result['overtimeFairness']
        self.assertEqual(f['total'], 22)
        self.assertEqual(f['byStaff'], {'s0': 5, 's1': 5, 's2': 3, 'd0': 3, 'd1': 3, 'd2': 3})
        self.assertEqual(f['balance'], 0)
        self.assertTrue(f['minimumSpreadProven'])
        self.assertTrue(result['allocation']['minimumOvertimeProven'])
        self.assertEqual(result['optimizationPolicy'], 'quality-first-9')

    def test_existing_candidate_can_be_reallocated_without_more_overtime(self):
        raw, before = overtime_fixture()
        for st in raw['staff'][:2]:
            st['overtimePreference'] = 2
        result = run(raw, initial_assignments=before)
        self.assertEqual(result['overtimeFairness']['byStaff'], {'s0': 5, 's1': 5, 's2': 3})
        self.assertEqual(result['allocation']['overtimeTotal'], 13)
        self.assertTrue(result['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(validate(raw, result['assignments']), [])

    def test_one_extra_and_two_extra_are_relative_preferences(self):
        raw, before = overtime_fixture()
        raw['staff'][0]['overtimePreference'] = 2
        raw['staff'][1]['overtimePreference'] = 1
        result = run(raw, initial_assignments=before)
        self.assertEqual(result['overtimeFairness']['total'], 13)
        self.assertEqual(result['overtimeFairness']['balance'], 1)
        self.assertTrue(result['overtimeFairness']['minimumSpreadProven'])
        self.assertGreaterEqual(result['overtimeFairness']['byStaff']['s0'], result['overtimeFairness']['byStaff']['s1'])

    def test_total_reduction_has_priority_over_welcome(self):
        raw, before = overtime_fixture()
        raw['staff'][0]['overtimePreference'] = 2
        raw['dailyRequiredStaff']['25'] = [1, 0, 1]
        result = run(raw, initial_assignments=before)
        self.assertEqual(result['allocation']['overtimeTotal'], 12)
        self.assertTrue(result['allocation']['minimumOvertimeProven'])

    def test_no_overtime_is_added_only_for_preference(self):
        raw, _ = overtime_fixture()
        raw['dailyRequiredStaff'] = {}
        raw['staff'][0]['overtimePreference'] = 2
        result = run(raw)
        self.assertEqual(result['allocation']['overtimeTotal'], 0)
        self.assertEqual(result['overtimeFairness']['balance'], 2)
        self.assertEqual(result['overtimeFairness']['idealBalance'], 2)
        self.assertTrue(result['overtimeFairness']['minimumSpreadProven'])

    def test_proportional_preference_and_cap_are_both_preserved(self):
        raw = leave_fixture()
        raw['staff'][2]['overtimePreference'] = 2
        p = normalize(raw)
        self.assertEqual(offsets(p, overtime_scales(p)), {'s0': 0, 's1': 0, 's2': 200})
        result = run(raw)
        self.assertEqual(result['overtimeFairness']['byStaff'], {'s0': 5, 's1': 5, 's2': 3})
        self.assertEqual(result['overtimeFairness']['balance'], 14)
        self.assertEqual(result['overtimeFairness']['idealBalance'], 14)
        self.assertTrue(result['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(validate(raw, result['assignments']), [])
        raw['shiftRequests'] = {'s2': {str(d): 'overtime' for d in (1, 3, 5, 7)}}
        self.assertEqual(run(raw)['status'], 'INFEASIBLE')

    def test_constraints_can_prevent_ideal_but_fixed_total_difference_is_proven(self):
        raw, before = overtime_fixture()
        raw['staff'][1]['overtimePreference'] = 2
        raw['shiftRequests'] = {'s2': {str(d): 'overtime' for d in (21, 23, 25)}}
        # s0に6回、s2に3回希望すると、歓迎のs1は4回になり算術理想の差1は達成できない。
        raw['shiftRequests']['s0'] = {str(d): 'overtime' for d in range(1, 12, 2)}
        result = run(raw, initial_assignments=before)
        self.assertEqual(result['allocation']['overtimeTotal'], 13)
        self.assertEqual(result['overtimeFairness']['balance'], 4)
        self.assertTrue(result['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(result['overtimeFairness']['reason'], 'constraints')
        self.assertEqual(validate(raw, result['assignments']), [])

    def test_timeout_does_not_claim_the_preference_cannot_be_improved(self):
        raw, before = overtime_fixture()
        raw['staff'][1]['overtimePreference'] = 2
        result = solve(raw, seconds=.000001, quality_first=True, initial_assignments=before,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(result['assignments'], before)
        self.assertFalse(result['overtimeFairness']['minimumSpreadProven'])

    def test_default_and_non_overtime_staff_do_not_change_metrics(self):
        raw, before = overtime_fixture()
        baseline = metrics(normalize(raw), before)
        for st in raw['staff']:
            st['overtimePreference'] = 0
        self.assertEqual(metrics(normalize(raw), before), baseline)
        raw['staff'][3]['overtimePreference'] = 2
        self.assertEqual(metrics(normalize(raw), before), baseline)

    def test_bad_values_are_rejected(self):
        raw, _ = overtime_fixture()
        for value in (None, True, '2', -1, 3, 1.5):
            raw['staff'][0]['overtimePreference'] = value
            with self.assertRaises(ValueError):
                normalize(raw)

    def test_preference_is_soft_in_independent_validation(self):
        raw, before = overtime_fixture()
        raw['staff'][1]['overtimePreference'] = 2
        self.assertEqual(validate(raw, before), [])

    def test_auto_calculation_and_inspection_ignore_preferences(self):
        raw, before = overtime_fixture()
        baseline = inspect(raw, before)
        raw['staff'][0]['overtimePreference'] = 2
        self.assertEqual(inspect(raw, before), baseline)
        policy = checked_policy(raw, {st['id']: {'min': 0, 'target': 0, 'max': 0, 'fixed': False} for st in raw['staff']})
        plan = HolidayPlan(raw, policy, 100000000000, baseline)
        self.assertNotIn('overtimePreference', plan.prepare()['staff'][0])
        # 境界で除去し、通常エンジンを呼ぶ場合も同じ入力になる。
        received = []
        def capture(payload, **kw):
            received.append(payload['input'])
            return {'status': 'UNKNOWN'}
        with patch('solver.service.dispatch', capture):
            from solver.auto_schedule import dispatch_auto
            dispatch_auto({'mode': 'auto', 'input': raw, 'seconds': 1, 'holidayPolicy': policy})
        self.assertTrue(received)
        self.assertNotIn('overtimePreference', received[0]['staff'][0])
        self.assertEqual(raw['staff'][0]['overtimePreference'], 2)

    def test_weights_have_room_with_maximum_preference_and_proportional_scales(self):
        for leave in (0, 12, 18, 22, 30):
            raw = {'year': 2026, 'month': 10, 'staff': [
                {'id': f's{i}', 'type': 'full', 'canOvertime': True, 'monthlyDaysOff': 9,
                 'overtimePreference': i % 3} for i in range(40)],
                'requests': {f's{i}': list(range(1, leave + 1)) for i in range(0, 40, 2)}}
            self.assertLess(weights(normalize(raw))[1] * 16, 2 ** 63 - 1)


class ArithmeticTests(unittest.TestCase):
    def test_exact_bound_matches_exhaustive_integer_allocations(self):
        # 負の目安、上限、比率、ゼロ出勤、全員歓迎なども含め総当たりと照合。
        for profiles in (
                ((1, 2, 6), (1, 0, 6), (1, 0, 6)),
                ((1, 2, 6), (1, 2, 6), (1, 0, 6)),
                ((100, 0, 6), (100, 0, 6), (238, 200, 3)),
                ((600, 200, 1), (100, 100, 6), (100, 0, 6)),
                ((1, 2, 0), (1, 1, 3)), ((1, 2, 6),),
                ((1, 2, 6), (1, 2, 6), (1, 2, 6))):
            expected = {}
            for counts in itertools.product(*(range(cap + 1) for _, _, cap in profiles)):
                scores = [count * scale - extra for count, (scale, extra, _) in zip(counts, profiles)]
                total, balance = sum(counts), max(scores) - min(scores)
                expected[total] = min(expected.get(total, balance), balance)
            for total, balance in expected.items():
                self.assertEqual(minimum_balance(profiles, total), balance, (profiles, total))
