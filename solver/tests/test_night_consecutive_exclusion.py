"""夜勤を連勤に数えない設定を計算と独立検査で一致させる。"""
from copy import deepcopy
import unittest
from unittest.mock import patch
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.service import check_resume
from solver.quality_search import search
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
    def test_common_rule_overrides_old_staff_settings_without_editing_input(self):
        raw = fixture()
        raw['excludeNightFromConsecutive'] = True
        raw['staff'][0]['excludeNightFromConsecutive'] = False
        raw['staff'][1]['excludeNightFromConsecutive'] = True
        before = deepcopy(raw)
        self.assertTrue(all(st['excludeNightFromConsecutive'] for st in normalize(raw)['staff']))
        raw['staff'][0].update(monthlyDaysOff=9, fixedDaysOff=True)
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        row = result['assignments']['s0']
        self.assertEqual([row[str(d)] for d in range(1, 6)], ['early', 'early', 'night', 'nightOff', 'off'])
        self.assertEqual(list(row.values()).count('off'), 9)
        self.assertEqual(validate(raw, result['assignments']), [])
        broken = deepcopy(result['assignments'])
        broken['s0']['4'] = 'early'
        self.assertTrue(any(e['code'] == 'night_link' for e in validate(raw, broken)))
        broken = deepcopy(result['assignments'])
        broken['s0']['5'] = 'early'
        self.assertTrue(any(e['code'] == 'night_rest' for e in validate(raw, broken)))
        self.assertEqual(raw['staff'][0]['excludeNightFromConsecutive'], before['staff'][0]['excludeNightFromConsecutive'])

    def test_common_rule_covers_boundary_and_plus_one_but_keeps_day_shift_limits(self):
        raw = fixture()
        raw['excludeNightFromConsecutive'] = True
        raw['history']['s0'] = ['off'] * 5 + ['early', 'early']
        raw['shiftRequests'] = {'s0': {'1': 'night'}}
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(validate(raw, result['assignments']), [])
        raw['history']['s0'] = ['off'] * 7
        raw['staff'][0]['allowConsecutivePlus1'] = True
        raw['shiftRequests'] = {'s0': {'1':'early','2':'early','3':'early','5':'early','6':'early','7':'night'}}
        raw['requests'] = {'s0': [4]}
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(validate(raw, result['assignments']), [])
        # 夜勤を除いても、日勤の＋1を2回に増やすことはできない。
        raw['shiftRequests']['s0']['7'] = 'early'
        self.assertEqual(solve(raw, seconds=5, allow_staffing_shortfall=True)['status'], 'INFEASIBLE')

    def test_common_rule_input_validation_and_legacy_resume(self):
        for value in (None, 1, 'true'):
            raw = fixture()
            raw['excludeNightFromConsecutive'] = value
            self.assertEqual(solve(raw, seconds=1)['status'], 'INVALID_INPUT')
        raw = fixture()
        raw['excludeNightFromConsecutive'] = True
        result = solve(raw, seconds=5, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        old = {'stage': 'placement', 'idle': 30, 'proven': {'conditions': True},
               'proofValues': {'conditions': [0]}, 'preservedCommonExtraDaysOff': 0}
        with patch('solver.engine.quality_search', wraps=search) as invoked:
            continued = solve(raw, seconds=.001, quality_first=True, allow_staffing_shortfall=True,
                              initial_assignments=result['assignments'], resume=old)
        passed = invoked.call_args.kwargs['resume']
        self.assertEqual((passed['stage'], passed['idle'], passed['proven'], passed['proofValues']),
                         ('conditions', 0, {}, {}))
        resume = continued['search']['resume']
        self.assertEqual(resume['nightConsecutivePolicy'], 'exclude-night-1')
        self.assertEqual(check_resume(resume, True)['nightConsecutivePolicy'], 'exclude-night-1')
        with self.assertRaises(ValueError):
            check_resume(dict(resume, nightConsecutivePolicy=42), True)

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
