"""中間ルール（連勤上限・連勤＋1・日勤の種類）、作れないときの理由、段階の止め方と続きの計算を確認する。"""
import unittest
from unittest.mock import patch
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_fairness import six_staff
from solver.tests.test_engine import fixture

SCREEN = {'qualityFirst': True, 'allowStaffingShortfall': True, 'allowRuleExceptions': True, 'seconds': 10}


class RuleExceptionTests(unittest.TestCase):
    def test_consecutive_limit_is_broken_only_as_much_as_wishes_require(self):
        raw = six_staff()
        raw['shiftRequests'] = {'s0': {str(d): 'early' for d in (3, 4, 5, 6)}}
        strict = dispatch(dict(SCREEN, input=raw, allowRuleExceptions=False))
        self.assertEqual(strict['status'], 'INFEASIBLE')
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['exceptionCount'], 1)
        self.assertEqual([(e['code'], e['staff'], e['day'], e['actual'], e['limit']) for e in r['ruleExceptions']],
                         [('consecutive', 's0', 6, 4, 3)])
        self.assertEqual([e['code'] for e in validate(raw, r['assignments'])], ['consecutive'])

    def test_plus_one_allowance_is_used_before_counting_an_exception(self):
        raw = six_staff()
        raw['staff'][0]['allowConsecutivePlus1'] = True
        raw['shiftRequests'] = {'s0': {str(d): 'early' for d in (3, 4, 5, 6, 12, 13, 14, 15)}}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['exceptionCount'], 1)
        self.assertEqual([e['code'] for e in r['ruleExceptions']], ['consecutive_plus_one'])

    def test_opposite_day_shift_only_for_staff_who_allow_it(self):
        raw = six_staff()
        raw['staff'][1]['dayShiftType'] = 'early'
        raw['shiftRequests'] = {'s1': {'4': 'late'}}
        self.assertEqual(dispatch(dict(SCREEN, input=raw))['status'], 'INFEASIBLE')
        raw['staff'][1]['dayShiftFlexible'] = True
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual([(e['code'], e['day']) for e in r['ruleExceptions']], [('day_shift_eligibility', 4)])
        # 許可していても、必要がなければ逆の日勤には入れない。
        raw['shiftRequests'] = {}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertNotIn('ruleExceptions', r)
        self.assertNotIn('late', r['assignments']['s1'].values())
        for bad in (1, 'yes', None):
            raw['staff'][1]['dayShiftFlexible'] = bad
            self.assertEqual(dispatch(dict(SCREEN, input=raw))['status'], 'INVALID_INPUT')

    def test_exceptions_are_never_used_to_reduce_staffing_shortfall(self):
        raw = six_staff()
        raw['requiredStaff'] = [5, 5, 5]
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'DRAFT')
        self.assertGreater(r['staffingShortfallTotal'], 0)
        self.assertNotIn('ruleExceptions', r)
        if 'shortfallLowerBound' in r:
            self.assertLessEqual(r['shortfallLowerBound'], r['staffingShortfallTotal'])

    def test_every_night_is_required_from_the_screen(self):
        raw = six_staff()
        for st in raw['staff']:
            st['nightShiftType'] = 'weekday'
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)
        # 2026年9月期の3日目は9月18日（金）。金土日は月〜木のみの人では埋まらない。
        self.assertEqual(r['diagnosis']['missingNights'][:3], [3, 4, 5])
        self.assertEqual(r['diagnosis']['droppedWishes'], [])

    def test_impossible_wishes_report_the_fewest_to_remove(self):
        raw = six_staff()
        raw['shiftRequests'] = {'s0': {'5': 'night'}, 's1': {'5': 'night'}}
        raw['requests'] = {'s2': [7]}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'INFEASIBLE')
        d = r['diagnosis']
        self.assertEqual(d['status'], 'EXPLAINED')
        self.assertTrue(d['proven'])
        self.assertEqual(d['missingNights'], [])
        self.assertEqual(len(d['droppedWishes']), 1)
        self.assertEqual(d['droppedWishes'][0]['day'], 5)
        self.assertEqual(d['droppedWishes'][0]['shift'], 'night')
        # 人数不足を許さない従来の厳密な作成では、理由調べは行わない。
        self.assertNotIn('diagnosis', dispatch({'input': raw, 'seconds': 5}))


class StageProgressTests(unittest.TestCase):
    def test_stalled_stage_moves_on_and_reaches_placement(self):
        raw = fixture(3)
        with patch.dict('solver.quality_search.IDLE_SECONDS', {'conditions': 0.5, 'overtime': 0.5, 'overtime_fairness': 0.5, 'placement': 0.5}):
            r = dispatch(dict(SCREEN, input=raw, seconds=30))
        stages = r['search']['stages']
        self.assertEqual([s['stage'] for s in stages], ['conditions', 'overtime', 'overtime_fairness', 'placement'])
        # 配置まで進んでも、偏りを未確認のまま完了とはしない。
        fair = r['overtimeFairness']
        if fair['minimumSpreadProven']:
            self.assertTrue(r['search']['done'])
            self.assertIsNone(r['search']['resume'])
        else:
            self.assertFalse(r['search']['done'])
            self.assertTrue(r['search']['continueRecommended'])
            self.assertEqual(r['search']['resume']['stage'], 'overtime_fairness')
            self.assertEqual(r['search']['resume']['idle'], 0)
            self.assertEqual(r['search']['reason'], 'overtime_fairness_unconfirmed')
        self.assertEqual([e for e in validate(raw, r['assignments']) if e['code'] not in ('coverage', 'sunday_limit')], [])

    def test_resume_continues_from_the_given_stage_without_worsening(self):
        raw = six_staff()
        raw['requiredStaff'] = [3, 3, 3]
        first = dispatch(dict(SCREEN, input=raw, seconds=3))
        self.assertIn('assignments', first)
        second = dispatch(dict(SCREEN, input=raw, seconds=3, initialAssignments=first['assignments'],
                               resume={'stage': 'placement', 'idle': 0, 'proven': {'conditions': True}}))
        self.assertEqual(second['search']['stages'][0]['stage'], 'placement')
        self.assertLessEqual(second.get('staffingShortfallTotal', 0), first.get('staffingShortfallTotal', 0))
        self.assertLessEqual(second['allocation']['overtimeTotal'], first['allocation']['overtimeTotal'])
        for bad in ({'stage': 'other'}, {'stage': 'overtime', 'idle': -1}, {'stage': 'overtime', 'x': 1},
                    {'stage': 'overtime', 'proven': {'overtime': 'yes'}}, 'overtime'):
            self.assertEqual(dispatch(dict(SCREEN, input=raw, resume=bad))['status'], 'INVALID_INPUT')
        self.assertEqual(dispatch({'input': raw, 'resume': {'stage': 'overtime'}})['status'], 'INVALID_INPUT')

    def test_timeout_inside_a_stage_returns_where_to_resume(self):
        raw = fixture(3)
        r = dispatch(dict(SCREEN, input=raw, seconds=2))
        self.assertFalse(r['search']['done'])
        self.assertTrue(r['search']['continueRecommended'])
        # 2秒でも条件段階を証明できる場合がある。速度に関係なく、
        # 未証明の現在段階と、完了した段階の証明を正しく持ち越すことを確認する。
        resume = r['search']['resume']
        order = ['conditions', 'overtime', 'overtime_fairness', 'placement']
        self.assertIn(resume['stage'], order)
        self.assertFalse(resume['proven'].get(resume['stage'], False))
        for stage in order[:order.index(resume['stage'])]:
            self.assertTrue(resume['proven'][stage])
        self.assertEqual(r['search']['reason'], f"{resume['stage']}_unconfirmed")
        self.assertGreaterEqual(r['search']['resume']['idle'], 0)


if __name__ == '__main__':
    unittest.main()
