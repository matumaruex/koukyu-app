"""連休なし（3.38）：計算が連休を作らないこと、希望休と前期の境目の扱い、数学的に無理なときだけ最少の例外を出すこと。"""
import unittest
from unittest.mock import patch
from solver.service import dispatch
from solver.input_data import normalize
from solver.validator import validate
from solver.tests.test_night_fairness import six_staff

SCREEN = {'qualityFirst': True, 'allowStaffingShortfall': True, 'allowRuleExceptions': True, 'seconds': 15}


def pairs(row, days):
    return [d for d in range(2, days + 1) if row[str(d)] == 'off' and row[str(d - 1)] == 'off']


def setting(**extra):
    raw = six_staff()
    raw['staff'][0].update({'noConsecutiveRest': True, **extra})
    return raw


def impossible():
    # 30日の期間で公休17日以上。出勤13日で区切れる公休のまとまりは最大13個なので、連続は最少4組（前期最終日の公休を含む）。
    raw = six_staff()
    raw['staff'][5].update(noConsecutiveRest=True, nightShiftType='none', monthlyDaysOff=17)
    raw['fairnessExcludedStaff'] = ['s5']
    return raw


class InputAndValidatorTests(unittest.TestCase):
    def test_input_is_checked(self):
        self.assertFalse(normalize(six_staff())['staff'][0]['noConsecutiveRest'])
        for bad in ('yes', 1, None):
            with self.assertRaises(ValueError):
                normalize(setting(noConsecutiveRest=bad))
        with self.assertRaises(ValueError):
            normalize(setting(minConsecutiveRest=1))

    def test_validator_counts_only_pairs_made_by_the_calculation(self):
        raw = setting()
        raw['requests'] = {'s0': [10, 11]}
        raw['locked'] = {'s0': {'20': 'off', '21': 'off'}}
        row = {str(d): 'early' for d in range(1, 31)}
        for d in (3, 4, 5, 10, 11, 20, 21, 24, 25):
            row[str(d)] = 'off'
        row['26'] = 'nightOff'
        row['27'] = 'off'
        a = {f's{i}': {str(d): 'off' if d % 2 else 'early' for d in range(1, 31)} for i in range(6)}
        a['s0'] = row
        found = [(e['start'], e['end'], e['count']) for e in validate(raw, a) if e['code'] == 'no_consecutive_rest']
        # 3〜5日は2組、24〜25日は1組。希望休どうし・固定の公休どうし・明けのあとの公休は数えない。
        self.assertEqual(found, [(3, 5, 2), (24, 25, 1)])
        # 前期の最終日が公休（入力あり）なら、今期1日目の公休とつながる。前期が未入力（仮定の休み）ならつなげない。
        row['1'] = 'off'
        raw['history'] = {'s0': ['early'] * 6 + ['off']}
        self.assertIn((0, 1, 1), [(e['start'], e['end'], e['count']) for e in validate(raw, a) if e['code'] == 'no_consecutive_rest'])
        raw['history'] = {}
        self.assertNotIn(0, [e['start'] for e in validate(raw, a) if e['code'] == 'no_consecutive_rest'])


class CalculationTests(unittest.TestCase):
    def test_no_consecutive_rest_for_that_staff_only(self):
        r = dispatch(dict(SCREEN, input=setting()))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(pairs(r['assignments']['s0'], 30), [])
        self.assertEqual(r['noConsecutiveRest']['minimum'], 0)
        self.assertNotIn('restExceptionCount', r)
        self.assertEqual(validate(setting(), r['assignments']), [])

    def test_consecutive_wishes_are_kept(self):
        raw = setting()
        raw['requests'] = {'s0': [10, 11]}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(pairs(r['assignments']['s0'], 30), [11])
        self.assertNotIn('restExceptionCount', r)
        self.assertEqual(r['assignments']['s0']['9'] != 'off' and r['assignments']['s0']['12'] != 'off', True)

    def test_previous_period_boundary(self):
        raw = setting()
        raw['history']['s0'] = ['early'] * 6 + ['off']
        r = dispatch(dict(SCREEN, input=raw))
        self.assertNotEqual(r['assignments']['s0']['1'], 'off')
        raw['requests'] = {'s0': [1]}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['assignments']['s0']['1'], 'off')
        self.assertNotIn('restExceptionCount', r)

    def test_only_proven_minimum_exceptions_when_impossible(self):
        r = dispatch(dict(SCREEN, input=impossible()))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE', 'DRAFT'))
        self.assertEqual(r['noConsecutiveRest'], {'minimum': 4, 'proven': True, 'seconds': r['noConsecutiveRest']['seconds']})
        self.assertEqual(r['restExceptionCount'], 4)
        self.assertTrue(r['restExceptionsProvenMinimum'])
        self.assertEqual(sum(e['count'] for e in r['ruleExceptions'] if e['code'] == 'no_consecutive_rest'), 4)
        self.assertEqual(r.get('exceptionCount', 0), 0)
        # 人数不足を許さない厳密な作成では、必ず守る条件なので作れない。
        self.assertEqual(dispatch({'input': impossible(), 'seconds': 10})['status'], 'INFEASIBLE')

    def test_unconfirmed_minimum_is_not_accepted(self):
        with patch('solver.engine.REST_PROOF_SECONDS', 0.000001):
            r = dispatch(dict(SCREEN, input=impossible()))
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertNotIn('assignments', r)
        self.assertTrue(r['search']['continueRecommended'])

    def test_without_the_setting_nothing_changes(self):
        r = dispatch(dict(SCREEN, input=six_staff()))
        self.assertNotIn('noConsecutiveRest', r)
        self.assertNotIn('restExceptionCount', r)


if __name__ == '__main__':
    unittest.main()
