"""長期休暇などで出勤できる日数が少ない人の残業：上限を比率で縮め、回数も比率で比べる（3.26）。"""
import unittest
from copy import deepcopy
from solver.engine import solve
from solver.service import dispatch
from solver.input_data import normalize, overtime_profile
from solver.allocation import metrics, overtime_scales, weights
from solver.validator import validate
from solver.tests.test_overtime_fairness import overtime_fixture

SCREEN = {'qualityFirst': True, 'allowStaffingShortfall': True, 'allowRuleExceptions': True, 'seconds': 10}


def profile(requests, days_off=9, month=12):
    p = normalize({'year': 2026, 'month': month, 'requests': {'a': requests},
                   'staff': [{'id': 'a', 'type': 'full', 'monthlyDaysOff': days_off}]})
    return overtime_profile(p, p['staff'][0])


def leave_fixture():
    # s2 は期間の14日目以降（18日）が希望休。出勤できる日数13日、普通の人は31日。
    raw, _ = overtime_fixture()
    raw['requests'] = {'s2': list(range(14, 32))}
    return raw


class ProfileTests(unittest.TestCase):
    def test_available_days_and_scaled_cap(self):
        # 31日の期間・最低9日の公休で、希望休18日なら出勤できる日数13日、上限は6×13/22を切り上げて4回。
        self.assertEqual(profile(list(range(1, 19))), {'available': 13, 'normal': 22, 'proportional': True, 'cap': 4})
        # 希望休が最低日数以内なら普通の人と同じ。重複した日付は1日と数える。
        self.assertEqual(profile([1, 2, 3, 3]), {'available': 22, 'normal': 22, 'proportional': False, 'cap': 6})
        self.assertEqual(profile(list(range(1, 10)))['proportional'], False)
        self.assertEqual(profile(list(range(1, 11)))['cap'], 6)
        self.assertEqual(profile(list(range(1, 32))), {'available': 0, 'normal': 22, 'proportional': True, 'cap': 0})
        self.assertEqual(profile([], days_off=31)['proportional'], False)

    def test_scales_only_change_when_someone_has_fewer_days(self):
        raw, _ = overtime_fixture()
        # 普通の人だけの月は全員1（3.25と同じ回数の差）。
        self.assertEqual(overtime_scales(normalize(raw)), {'s0': 1, 's1': 1, 's2': 1})
        # 出勤できる日数13日・普通31日の人がいれば、普通の人100、その人は100×31÷13を四捨五入して238。
        self.assertEqual(overtime_scales(normalize(leave_fixture())), {'s0': 100, 's1': 100, 's2': 238})

    def test_worst_case_weights_fit_in_64_bit_integers(self):
        # 40人・31日、全員がA残でき、出勤できる日数がとても少ない最悪の場合でも、評価値の上限に16倍の余裕がある。
        for leave in (30, 22, 18, 12):
            raw = {'year': 2026, 'month': 12,
                   'staff': [{'id': f's{i}', 'type': 'full', 'canOvertime': True, 'monthlyDaysOff': 9} for i in range(40)],
                   'requests': {f's{i}': list(range(1, leave + 1)) for i in range(0, 40, 2)}}
            _, total = weights(normalize(raw))
            self.assertLess(total * 16, 2 ** 63 - 1)

    def test_validator_uses_the_scaled_cap(self):
        raw = leave_fixture()
        a = {sid: {str(d): 'off' for d in range(1, 32)} for sid in ('s0', 's1', 's2', 's3', 's4', 's5')}
        for d in (1, 3, 5, 7):
            a['s2'][str(d)] = 'overtime'
        errors = [e for e in validate(raw, a) if e['code'] == 'overtime_limit']
        self.assertEqual([(e['staff'], e['actual'], e['limit']) for e in errors], [('s2', 4, 3)])
        a['s2']['7'] = 'off'
        self.assertEqual([e for e in validate(raw, a) if e['code'] == 'overtime_limit'], [])


class ProportionalOvertimeTests(unittest.TestCase):
    def test_fewer_available_days_get_a_proportional_share(self):
        raw = leave_fixture()
        r = solve(raw, seconds=10, quality_first=True, allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(validate(raw, r['assignments']), [])
        f = r['overtimeFairness']
        self.assertEqual(f['total'], 13)
        # 合計13回を 31日・31日・13日 で分ける。比率で最も均等なのは 6・5・2（3.25の数え方なら 5・4・4）。
        self.assertEqual(f['byStaff']['s2'], 2)
        self.assertEqual(sorted([f['byStaff']['s0'], f['byStaff']['s1']]), [5, 6])
        self.assertEqual(f['proportionalStaff'], {'s2': {'availableDays': 13, 'normalDays': 31, 'cap': 3}})
        self.assertEqual(f['spread'], 1)
        self.assertIsNone(f['idealSpread'])
        self.assertTrue(f['minimumSpreadProven'])
        self.assertEqual(f['reason'], 'constraints')

    def test_cap_is_absolute_and_too_many_wishes_are_explained(self):
        raw = leave_fixture()
        raw['shiftRequests'] = {'s2': {str(d): 'overtime' for d in (1, 3, 5, 7)}}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertEqual(len(r['diagnosis']['droppedWishes']), 1)
        self.assertEqual(r['diagnosis']['droppedWishes'][0]['staff'], 's2')
        raw['shiftRequests']['s2'].pop('7')
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['overtimeFairness']['byStaff']['s2'], 3)

    def test_without_long_leave_nothing_changes(self):
        raw, before = overtime_fixture()
        p = normalize(raw)
        m = metrics(p, before)
        self.assertFalse(m['overtimeProportional'])
        self.assertEqual(m['overtimeBalance'], m['overtimeSpread'])
        self.assertEqual(m['overtimeIdealBalance'], 1)
        r = solve(raw, seconds=5, quality_first=True, initial_assignments=before,
                  allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(sorted(r['overtimeFairness']['byStaff'].values()), [4, 4, 5])
        self.assertEqual(r['overtimeFairness']['proportionalStaff'], {})
        self.assertEqual(r['overtimeFairness']['idealSpread'], 1)

    def test_staff_who_cannot_work_are_not_compared(self):
        raw = leave_fixture()
        raw['requests'] = {'s2': list(range(1, 32))}
        raw['dailyRequiredStaff'] = {k: [1, 1, 1] for k in raw['dailyRequiredStaff']}
        for sid in raw['locked']:
            for d in range(1, 32):
                if raw['locked'][sid].get(str(d)) == 'overtime':
                    raw['locked'][sid].pop(str(d))
        r = solve(raw, seconds=5, quality_first=True, allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertIn('assignments', r)
        self.assertEqual(r['overtimeFairness']['byStaff']['s2'], 0)
        self.assertEqual(r['overtimeFairness']['proportionalStaff']['s2']['cap'], 0)
        self.assertEqual(validate(raw, r['assignments']), [])


if __name__ == '__main__':
    unittest.main()
