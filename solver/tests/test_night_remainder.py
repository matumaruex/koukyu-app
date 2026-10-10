"""夜勤の端数優先（3.39）：割り切れないときの多いほうを優先の人へ。無理なときだけ最少回数を例外にする。"""
import unittest
from unittest.mock import patch
from solver.service import dispatch
from solver.input_data import normalize
from solver.night_remainder import plan, report, max_nights
from solver.validator import validate
from solver.overtime_preference import without_preferences
from solver.tests.test_night_fairness import six_staff

SCREEN = {'qualityFirst': True, 'allowStaffingShortfall': True, 'allowRuleExceptions': True, 'seconds': 20}


def nights(r):
    return {sid: list(row.values()).count('night') for sid, row in r['assignments'].items()}


def priority(*sids, month=10):
    # 2026年10月期は31日。夜勤できる6人で割ると基準5回・端数1回（6・5・5・5・5・5）。
    raw = six_staff(month)
    for st in raw['staff']:
        st['nightRemainderPriority'] = st['id'] in sids
    return raw


class PlanTests(unittest.TestCase):
    def test_base_extras_and_allowance(self):
        p = normalize(priority('s3'))
        self.assertEqual(plan(p), {'base': 5, 'extras': 1, 'priority': ['s3'],
                                   'fair': {'s0': 5, 's1': 5, 's2': 5, 's3': 6, 's4': 5, 's5': 5}, 'allowance': 0})
        # 9月期（30日）は割り切れる。優先の人も目安は基準＋1回まで。
        self.assertEqual(plan(normalize(priority('s3', month=9)))['extras'], 0)
        # 優先の人がいなければ使わない。夜勤なし・パートは対象外。
        self.assertIsNone(plan(normalize(six_staff(10))))
        raw = priority('s3')
        raw['staff'][3]['nightShiftType'] = 'none'
        self.assertIsNone(plan(normalize(raw)))
        for bad in ('yes', 1):
            raw = priority('s3')
            raw['staff'][3]['nightRemainderPriority'] = bad
            with self.assertRaises(ValueError):
                normalize(raw)

    def test_allowance_when_more_extras_than_priority_staff(self):
        raw = priority('s3')
        raw['staff'] = raw['staff'][:4]
        raw['history'] = {st['id']: ['off'] * 7 for st in raw['staff']}
        p = normalize(raw)
        # 31÷4＝基準7回・端数3回。優先の人が1人なら、残り2回はほかの人へ行くのが避けられない。
        self.assertEqual((plan(p)['base'], plan(p)['extras'], plan(p)['allowance']), (7, 3, 2))

    def test_validator_reports_only_exceptions_beyond_allowance(self):
        raw = priority('s3')
        a = {f's{i}': {str(d): 'off' for d in range(1, 32)} for i in range(6)}
        counts = {'s0': 6, 's1': 5, 's2': 5, 's3': 5, 's4': 5, 's5': 5}
        for sid, c in counts.items():
            for k in range(c):
                a[sid][str(1 + k * 3 + int(sid[1]) % 3)] = 'night'
        errors = [e for e in validate(raw, a) if e['code'] == 'night_remainder']
        self.assertEqual([(e['staff'], e['actual'], e['fair'], e['count']) for e in errors], [('s0', 6, 5, 1)])
        self.assertEqual(report(normalize(raw), a)['exceptions'], 1)

    def test_max_nights_is_a_safe_upper_bound(self):
        raw = priority('s3')
        raw['requests'] = {'s3': list(range(1, 20))}
        p = normalize(raw)
        # 期間の20日目以降の12日間だけ。夜勤→明け→公休で、最大4回。
        self.assertEqual(max_nights(p, p['staff'][3]), 4)
        self.assertGreaterEqual(max_nights(p, p['staff'][0]), 6)


class CalculationTests(unittest.TestCase):
    def test_extra_night_goes_to_the_priority_staff(self):
        for sid in ('s3', 's0'):
            r = dispatch(dict(SCREEN, input=priority(sid)))
            self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
            self.assertEqual(nights(r)[sid], 6)
            self.assertEqual(sorted(nights(r).values()), [5, 5, 5, 5, 5, 6])
            self.assertEqual(r['nightRemainder']['exceptions'], 0)
            self.assertTrue(r['nightRemainder']['proven'])
            self.assertNotIn('nightRemainderExceptions', r)

    def test_proven_minimum_exceptions_when_the_priority_staff_cannot(self):
        raw = priority('s3')
        raw['requests'] = {'s3': list(range(1, 20))}
        raw['fairnessExcludedStaff'] = ['s3']
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(nights(r)['s3'], 4)
        # 優先の人が受け持てない分（6−4＝2回）だけ、ほかの人が目安を超える。最少と証明して例外にする。
        self.assertEqual(r['nightRemainderExceptions'], 2)
        self.assertTrue(r['nightRemainder']['proven'])
        self.assertEqual(sum(e['count'] for e in r['ruleExceptions'] if e['code'] == 'night_remainder'), 2)
        # 厳密な作成では必ず守る条件なので作れない。
        self.assertEqual(dispatch({'input': raw, 'seconds': 10})['status'], 'INFEASIBLE')

    def test_unconfirmed_minimum_is_not_accepted(self):
        raw = priority('s3')
        with patch('solver.engine.REST_PROOF_SECONDS', 0.000001):
            r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertNotIn('assignments', r)
        self.assertTrue(r['search']['continueRecommended'])

    def test_auto_mode_and_unset_are_unchanged(self):
        self.assertNotIn('nightRemainderPriority', without_preferences(priority('s3'))['staff'][3])
        r = dispatch(dict(SCREEN, input=six_staff(10)))
        self.assertNotIn('nightRemainder', r)


if __name__ == '__main__':
    unittest.main()
