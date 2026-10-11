"""連休の回数の差（3.46）：連休の設定をした人どうしで1回以内。数学的に無理なときだけ最少回数を例外にする。
希望休・固定の公休だけでできた連休は数えない。公休の比較から外した人は比べない。"""
import copy
import unittest
from unittest.mock import patch
from solver.service import dispatch
from solver.input_data import normalize
from solver.rest_blocks import counted_ranges, balance_report
from solver.validator import validate, is_rule_exception, exception_count
from solver.overtime_preference import without_preferences
from solver.tests.test_night_fairness import six_staff

SCREEN = {'qualityFirst': True, 'allowStaffingShortfall': True, 'allowRuleExceptions': True, 'seconds': 20}


def with_rest(raw, sids=('s0', 's1'), flag=True):
    raw['restCountBalance'] = flag
    for st in raw['staff']:
        if st['id'] in sids:
            st['minConsecutiveRest'] = 1
    return raw


def row(offs, days=30):
    return {str(d): 'off' if d in offs else 'early' for d in range(1, days + 1)}


def counted(r, p):
    return {sid: len(counted_ranges(p, sid, r['assignments'][sid])) for sid in ('s0', 's1')}


class ReportTests(unittest.TestCase):
    def test_wish_only_blocks_are_not_counted(self):
        raw = with_rest(six_staff())
        raw['requests'] = {'s0': [4, 5, 10]}
        raw['locked'] = {'s0': {'15': 'off', '16': 'off'}}
        p = normalize(raw)
        blocks = counted_ranges(p, 's0', row({4, 5, 10, 11, 15, 16, 20, 21}))
        # 4〜5日（希望休だけ）と15〜16日（固定の公休だけ）は数えない。10〜11日は計算が決めた11日を含むので数える。
        self.assertEqual(blocks, [{'start': 10, 'end': 11}, {'start': 20, 'end': 21}])

    def test_compared_staff(self):
        raw = with_rest(six_staff())
        a = {f's{i}': row({3, 4} if i else {3, 4, 10, 11, 20, 21}) for i in range(6)}
        found = balance_report(normalize(raw), a)
        self.assertEqual((found['counts'], found['excess']), ({'s0': 3, 's1': 1}, 1))
        # 指定がない入力、比べる人が1人だけ、公休の比較から外した人は対象外。
        self.assertIsNone(balance_report(normalize(with_rest(six_staff(), flag=False)), a))
        self.assertIsNone(balance_report(normalize(with_rest(six_staff(), sids=('s0',))), a))
        raw['fairnessExcludedStaff'] = ['s0']
        self.assertIsNone(balance_report(normalize(raw), a))
        for bad in ('yes', 1):
            with self.assertRaises(ValueError):
                normalize(dict(six_staff(), restCountBalance=bad))
        self.assertNotIn('restCountBalance', without_preferences(with_rest(six_staff())))

    def test_validator_reports_one_exception(self):
        raw = with_rest(six_staff())
        a = {f's{i}': row({3, 4} if i else {3, 4, 10, 11, 20, 21}) for i in range(6)}
        errors = [e for e in validate(raw, a) if e['code'] == 'rest_balance']
        self.assertEqual([(e['high'], e['low'], e['count']) for e in errors], [(3, 1, 1)])
        p = normalize(raw)
        self.assertTrue(is_rule_exception(p, errors[0]))
        self.assertEqual(exception_count(p, errors), 0)


class CalculationTests(unittest.TestCase):
    def test_kept_within_one(self):
        raw = with_rest(six_staff(10), sids=('s0', 's1', 's2', 's3'))
        raw['requests'] = {'s0': [4, 12, 21], 's2': [7, 16]}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['restBalance']['excess'], 0)
        self.assertTrue(r['restBalance']['proven'])
        counts = r['restBalance']['counts']
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        p = normalize(raw)
        self.assertEqual(counts, {sid: len(counted_ranges(p, sid, r['assignments'][sid])) for sid in counts})
        self.assertNotIn('restBalanceExceptions', r)

    def test_proven_minimum_exception_when_impossible(self):
        raw = with_rest(six_staff())
        # s0：夜勤→明け→公休のあとに希望休が続くので、計算が決めた公休を含む連休が必ず3回できる。
        raw['locked'] = {'s0': {'1': 'night', '8': 'night', '15': 'night'},
                         's1': {str(d): 'early' for d in range(1, 31) if d not in (20, 21)}}
        raw['requests'] = {'s0': [4, 11, 18]}
        # s1：休めるのは20〜21日だけなので連休は1回。差を1回以内にできない。
        raw['staff'][1].update(nightShiftType='none', monthlyDaysOff=2)
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['restBalanceExceptions'], 1)
        self.assertTrue(r['restBalance']['proven'])
        self.assertEqual(r['restBalance']['counts']['s1'], 1)
        self.assertEqual(r['restBalance']['counts']['s0'], 3)
        self.assertEqual([e['count'] for e in r['ruleExceptions'] if e['code'] == 'rest_balance'], [1])

    def test_unconfirmed_minimum_is_not_accepted(self):
        raw = with_rest(six_staff())
        with patch('solver.engine.REST_PROOF_SECONDS', 0.000001):
            r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertNotIn('assignments', r)
        self.assertTrue(r['search']['continueRecommended'])

    def test_unset_is_unchanged(self):
        r = dispatch(dict(SCREEN, input=with_rest(six_staff(), flag=False)))
        self.assertNotIn('restBalance', r)


if __name__ == '__main__':
    unittest.main()
