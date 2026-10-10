"""A残は1回の出勤サイクルに1回まで（3.40）：人数不足を減らすためだけに2回目を許す。希望・固定のA残も数える。"""
import copy
import unittest
from solver.service import dispatch
from solver.input_data import normalize
from solver.overtime_cycles import report
from solver.overtime_preference import without_preferences
from solver.tests.test_night_fairness import six_staff

SCREEN = {'qualityFirst': True, 'allowStaffingShortfall': True, 'allowRuleExceptions': True, 'seconds': 20}


def fixture(flag=True):
    """s0 は1〜3日目が同じサイクル（2日目は早出で固定、連勤上限3日）。全員Aのみ（Bは不可）。
    1日目は夜勤 s1 のほかに朝1人・夕1人が必要で、両方を埋められるのは s0 のA残だけ。
    3日目は明け s2・夜勤 s4 のほかに朝1人・夕1人が必要で、s0 か s3 のA残で埋まる。"""
    raw = six_staff()
    raw['overtimeCycleLimit'] = flag
    for st in raw['staff']:
        st['dayShiftType'] = 'early'
    raw['locked'] = {'s0': {'2': 'early'}, 's1': {'1': 'night'}, 's2': {'1': 'off', '2': 'night'},
                     's3': {'1': 'off'}, 's4': {'1': 'off', '3': 'night'}, 's5': {'1': 'off', '3': 'off'}}
    raw['dailyRequiredStaff'] = {'1': [1, 0, 2], '3': [2, 0, 2]}
    return raw


def row(shifts, days=30):
    out = {str(d): 'early' for d in range(1, days + 1)}
    out.update({str(d): k for d, k in shifts.items()})
    return out


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.raw = six_staff()
        self.raw['overtimeCycleLimit'] = True

    def counts(self, s0, raw=None):
        raw = raw or self.raw
        p = normalize(raw)
        a = {st['id']: row({d: 'off' for d in range(1, 31, 4)}) for st in p['staff']}
        a['s0'] = row(s0)
        return report(p, a)

    def test_cycles_are_split_by_off_and_night_recovery(self):
        # 公休・明けで区切る。夜勤は同じサイクルに含む。
        self.assertEqual(self.counts({1: 'overtime', 3: 'overtime', 4: 'off'})['items'],
                         [{'staff': 's0', 'start': 1, 'end': 3, 'overtime': 2, 'count': 1, 'wishOnly': False}])
        self.assertEqual(self.counts({1: 'overtime', 2: 'off', 3: 'overtime'})['excess'], 0)
        self.assertEqual(self.counts({1: 'overtime', 2: 'night', 3: 'nightOff', 4: 'off', 5: 'overtime'})['excess'], 0)
        self.assertEqual(self.counts({1: 'overtime', 3: 'night', 4: 'nightOff', 5: 'off'})['excess'], 0)
        self.assertEqual(self.counts({1: 'overtime', 3: 'overtime', 5: 'overtime', 6: 'off'})['excess'], 2)

    def test_requested_and_locked_overtime_are_counted(self):
        raw = copy.deepcopy(self.raw)
        raw['shiftRequests'] = {'s0': {'1': 'overtime'}}
        raw['locked'] = {'s0': {'3': 'overtime'}}
        # 希望・固定のA残も数える。計算が入れたA残がないサイクルは wishOnly。
        self.assertEqual(self.counts({1: 'overtime', 3: 'overtime', 4: 'off'}, raw)['items'],
                         [{'staff': 's0', 'start': 1, 'end': 3, 'overtime': 2, 'count': 1, 'wishOnly': True}])
        found = self.counts({1: 'overtime', 3: 'overtime', 5: 'overtime', 6: 'off'}, raw)
        self.assertEqual((found['excess'], found['items'][0]['wishOnly']), (2, False))

    def test_history_is_connected_only_when_entered(self):
        raw = copy.deepcopy(self.raw)
        raw['history']['s0'] = ['off'] * 5 + ['overtime', 'early']
        self.assertEqual(self.counts({2: 'overtime', 3: 'off'}, raw)['excess'], 1)
        raw['history']['s0'] = ['off'] * 4 + ['overtime', 'off', 'early']
        self.assertEqual(self.counts({2: 'overtime', 3: 'off'}, raw)['excess'], 0)
        del raw['history']['s0']
        self.assertEqual(self.counts({2: 'overtime', 3: 'off'}, raw)['excess'], 0)

    def test_disabled_and_validation(self):
        self.raw['overtimeCycleLimit'] = False
        self.assertIsNone(self.counts({1: 'overtime', 3: 'overtime'}))
        for bad in ('yes', 1):
            with self.assertRaises(ValueError):
                normalize(dict(self.raw, overtimeCycleLimit=bad))
        # おまかせには送らない。
        self.assertNotIn('overtimeCycleLimit', without_preferences(dict(self.raw, overtimeCycleLimit=True)))


class CalculationTests(unittest.TestCase):
    def test_second_overtime_only_to_reduce_shortfall(self):
        raw = fixture()
        raw['locked']['s3']['3'] = 'off'
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        # 3日目を埋められるのは s0 のA残だけ。人数不足を出さないために2回目を許す。
        self.assertEqual(r.get('staffingShortfallTotal', 0), 0)
        self.assertEqual(r['overtimeCycleExcess'], 1)
        self.assertEqual([(i['staff'], i['start'], i['count']) for i in r['overtimeCycles']['items']], [('s0', 1, 1)])
        self.assertTrue(r['overtimeCycles']['minimumProven'])

    def test_avoided_when_someone_else_can_cover(self):
        raw = fixture()
        # s0 を残業多めにして、規則がなければ s0 に2回入るほうが配分の目安に近い条件にする。
        raw['staff'][0]['overtimePreference'] = 2
        off = dispatch(dict(SCREEN, input=fixture(False) | {'staff': raw['staff']}))
        self.assertEqual(report(normalize(dict(fixture(), staff=raw['staff'])), off['assignments'])['excess'], 1)
        on = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(on.get('staffingShortfallTotal', 0), 0)
        self.assertEqual(on['overtimeCycleExcess'], 0)
        self.assertEqual(on['assignments']['s3']['3'], 'overtime')
        self.assertEqual(on['allocation']['overtimeTotal'], off['allocation']['overtimeTotal'])

    def test_requested_pair(self):
        raw = fixture()
        raw['locked']['s3']['3'] = 'off'
        raw['shiftRequests'] = {'s0': {'1': 'overtime', '3': 'overtime'}}
        # 間の日が早出で固定されていて分けられない：希望どおり入れて、2回目として数える。
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual((r['assignments']['s0']['1'], r['assignments']['s0']['3']), ('overtime', 'overtime'))
        self.assertEqual(r['overtimeCycleExcess'], 1)
        self.assertTrue(r['overtimeCycles']['items'][0]['wishOnly'])
        # 間の日が空いていれば、公休を入れてサイクルを分ける。
        del raw['locked']['s0']
        r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['overtimeCycleExcess'], 0)
        self.assertIn(r['assignments']['s0']['2'], ('off', 'nightOff'))

    def test_unset_is_unchanged(self):
        r = dispatch(dict(SCREEN, input=fixture(False)))
        self.assertNotIn('overtimeCycles', r)
        self.assertNotIn('overtimeCycleExcess', r)


if __name__ == '__main__':
    unittest.main()
