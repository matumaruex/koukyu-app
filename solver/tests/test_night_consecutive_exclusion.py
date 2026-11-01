"""夜勤を連勤に数えない設定を計算と独立検査で一致させる。"""
from copy import deepcopy
import unittest
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.tests.test_night_fairness import six_staff


def fixture():
    raw = six_staff()
    for st in raw['staff']:
        st['monthlyDaysOff'] = 0
        st['maxConsecutive'] = 6
    raw['staff'][0]['maxConsecutive'] = 2
    raw['fairnessExcludedStaff'] = [s['id'] for s in raw['staff']]
    raw['shiftRequests'] = {'s0': {'1': 'early', '2': 'early', '3': 'night'}}
    return raw

class NightConsecutiveTests(unittest.TestCase):
    def test_old_default_and_invalid_settings(self):
        raw = fixture()
        self.assertFalse(normalize(raw)['staff'][0]['excludeNightFromConsecutive'])
        for v in (None, 1, 'true'):
            bad = deepcopy(raw); bad['staff'][0]['excludeNightFromConsecutive'] = v
            self.assertEqual(solve(bad, seconds=1)['status'], 'INVALID_INPUT')

    def test_two_day_shifts_then_night_is_allowed_only_when_selected(self):
        raw = fixture()
        self.assertEqual(solve(raw, seconds=5, allow_staffing_shortfall=True)['status'], 'INFEASIBLE')
        raw['staff'][0]['excludeNightFromConsecutive'] = True
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        row = result['assignments']['s0']
        self.assertEqual([row[str(d)] for d in range(1, 6)], ['early', 'early', 'night', 'nightOff', 'off'])
        self.assertEqual(validate(raw, result['assignments']), [])
        old = deepcopy(raw); old['staff'][0]['excludeNightFromConsecutive'] = False
        self.assertTrue(any(e['code'] == 'consecutive' and e['staff'] == 's0' and e['day'] == 3 for e in validate(old, result['assignments'])))

    def test_previous_period_and_plus_one_are_counted_consistently(self):
        raw = fixture(); raw['staff'][0]['excludeNightFromConsecutive'] = True
        raw['history']['s0'] = ['off'] * 5 + ['early', 'early']
        raw['shiftRequests'] = {'s0': {'1': 'night'}}
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(result['assignments']['s0']['1'], 'night')
        self.assertEqual(validate(raw, result['assignments']), [])
        old = deepcopy(raw); old['staff'][0]['excludeNightFromConsecutive'] = False
        self.assertTrue(any(e['code'] == 'consecutive' and e['staff'] == 's0' and e['day'] == 1 for e in validate(old, result['assignments'])))
        raw['history']['s0'] = ['off'] * 7
        raw['staff'][0]['allowConsecutivePlus1'] = True
        raw['shiftRequests'] = {'s0': {'1':'early','2':'early','3':'early','5':'early','6':'early','7':'night'}}
        raw['requests'] = {'s0': [4]}
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(validate(raw, result['assignments']), [])
        old = deepcopy(raw); old['staff'][0]['excludeNightFromConsecutive'] = False
        self.assertTrue(any(e['code'] == 'consecutive_plus_one' and e['staff'] == 's0' for e in validate(old, result['assignments'])))
