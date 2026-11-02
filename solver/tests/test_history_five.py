"""前期5日、旧7日の保持、週上限の廃止と確認範囲を検査する。"""
from copy import deepcopy
import unittest
from unittest.mock import patch
from solver.input_data import normalize
from solver.engine import solve
from solver.validator import validate
from solver.service import check_resume, dispatch
from solver.quality_search import search
from solver.overtime_cycles import carry_in
from solver.tests.test_night_fairness import six_staff


def fixture():
    raw = six_staff(8)  # 8月16日（日）。旧週上限では前週の実績も必要。
    raw.update(partWeeklyLimit=False, excludeNightFromConsecutive=True)
    raw['history'] = {st['id']: ['off'] * 5 for st in raw['staff']}
    return raw


class FiveDayHistoryTests(unittest.TestCase):
    def test_five_days_and_legacy_seven_are_valid_without_editing_input(self):
        raw = fixture()
        raw['history']['s1'] = ['early', 'off'] + ['off'] * 5
        original = deepcopy(raw)
        p = normalize(raw)
        self.assertEqual(raw, original)
        self.assertTrue(p['boundaryComplete'])
        self.assertEqual(p['historyVerification']['providedDays']['s0'], 5)
        self.assertEqual(p['historyVerification']['providedDays']['s1'], 7)
        self.assertEqual(p['history']['s1'], original['history']['s1'])
        for size in (0, 1, 4, 6, 8):
            bad = deepcopy(raw); bad['history']['s0'] = ['off'] * size
            self.assertEqual(solve(bad, seconds=1)['status'], 'INVALID_INPUT')
        for value in (None, 1, 'false'):
            bad = deepcopy(raw); bad['partWeeklyLimit'] = value
            self.assertEqual(solve(bad, seconds=1)['status'], 'INVALID_INPUT')

    def test_part_weekly_limit_is_removed_from_model_and_validator(self):
        raw = fixture()
        raw['staff'].append({'id': 'p', 'type': 'part', 'nightShiftType': 'none',
                             'monthlyDaysOff': 0, 'maxConsecutive': 3, 'maxDaysPerWeek': 1,
                             'startTime': '09:00', 'endTime': '17:00'})
        raw['history']['p'] = ['off'] * 5
        raw['fairnessExcludedStaff'] = [st['id'] for st in raw['staff']]
        raw['locked'] = {'p': {'2': 'part', '3': 'part'}}
        result = solve(raw, seconds=5, optimize=False, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(validate(raw, result['assignments']), [])
        self.assertEqual(result['assignments']['p']['2'], 'part')
        legacy = deepcopy(raw); del legacy['partWeeklyLimit']
        self.assertEqual(solve(legacy, seconds=5, optimize=False, allow_staffing_shortfall=True)['status'], 'INFEASIBLE')
        self.assertTrue(any(e['code'] == 'weekly' for e in validate(legacy, result['assignments'])))
        broken = deepcopy(result['assignments']); broken['p']['2'] = 'early'
        self.assertTrue(any(e['code'] == 'eligibility' for e in validate(raw, broken)))
        raw['locked']['p'].update({'4': 'part', '5': 'part'})
        self.assertEqual(solve(raw, seconds=5, optimize=False, allow_staffing_shortfall=True)['status'], 'INFEASIBLE')

    def test_night_recovery_and_rest_continue_from_five_days(self):
        raw = fixture(); raw['history']['s0'][-1] = 'night'
        result = solve(raw, seconds=5, optimize=False, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertEqual([result['assignments']['s0'][str(d)] for d in (1, 2)], ['nightOff', 'off'])
        self.assertEqual(validate(raw, result['assignments']), [])
        self.assertTrue(result['boundaryComplete'])
        checked = dispatch({'action': 'validate', 'input': raw, 'assignments': result['assignments']})
        self.assertEqual(checked['status'], 'VALID')
        self.assertEqual(checked['historyVerification']['providedDays']['s0'], 5)

    def test_long_unbroken_history_is_not_claimed_fully_verified(self):
        raw = fixture(); raw['staff'][0].update(maxConsecutive=6, canOvertime=False)
        raw['history']['s0'] = ['early'] * 5
        p = normalize(raw)
        self.assertFalse(p['boundaryComplete'])
        issue = p['historyVerification']['issues'][0]
        self.assertEqual((issue['staff'], issue['provided'], issue['required']), ('s0', 5, 6))
        self.assertEqual(issue['reasons'], ['consecutive'])
        result = solve(raw, seconds=5, optimize=False, allow_staffing_shortfall=True)
        self.assertIn('assignments', result, result)
        self.assertFalse(result['boundaryComplete'])
        self.assertEqual(result['verificationScope'], 'PERIOD_ONLY')
        self.assertEqual(result['historyVerification'], p['historyVerification'])
        raw['history']['s0'][1] = 'off'
        raw['staff'][0]['allowConsecutivePlus1'] = True
        self.assertTrue(normalize(raw)['boundaryComplete'])

    def test_overtime_carry_is_known_only_with_a_reset_or_overtime(self):
        raw = fixture(); raw['overtimeCycleLimit'] = True
        raw['history']['s0'] = ['early'] * 5
        self.assertEqual(normalize(raw)['historyVerification']['issues'][0]['reasons'], ['overtime_cycle'])
        raw['history']['s0'][-1] = 'overtime'
        p = normalize(raw)
        self.assertTrue(p['boundaryComplete']); self.assertEqual(carry_in(p, 's0'), 1)
        raw['history']['s0'][-1] = 'off'
        p = normalize(raw)
        self.assertTrue(p['boundaryComplete']); self.assertEqual(carry_in(p, 's0'), 0)

    def test_missing_history_and_legacy_weekly_boundary_remain_unconfirmed(self):
        raw = fixture(); del raw['history']['s0']
        self.assertEqual(normalize(raw)['historyVerification']['issues'][0]['reasons'], ['missing'])
        raw['staff'] = [{'id': 'p', 'type': 'part', 'maxDaysPerWeek': 3,
                         'startTime': '09:00', 'endTime': '17:00'}]
        raw['history'] = {'p': ['off'] * 5}
        self.assertTrue(normalize(raw)['boundaryComplete'])
        del raw['partWeeklyLimit']
        self.assertEqual(normalize(raw)['historyVerification']['issues'][0]['reasons'], ['weekly'])

    def test_old_resume_restarts_and_new_history_policy_round_trips(self):
        raw = fixture()
        before = solve(raw, seconds=5, optimize=False, allow_staffing_shortfall=True)
        self.assertIn('assignments', before, before)
        old = {'stage': 'placement', 'idle': 30, 'proven': {'conditions': True},
               'proofValues': {'conditions': [0]}, 'preservedCommonExtraDaysOff': 0,
               'nightConsecutivePolicy': 'exclude-night-1'}
        with patch('solver.engine.quality_search', wraps=search) as invoked:
            result = solve(raw, seconds=.001, quality_first=True, allow_staffing_shortfall=True,
                           initial_assignments=before['assignments'], resume=old)
        passed = invoked.call_args.kwargs['resume']
        self.assertEqual((passed['stage'], passed['idle'], passed['proven']), ('conditions', 0, {}))
        resume = result['search']['resume']
        self.assertEqual(check_resume(resume, True)['historyPolicy'], 'five-day-no-weekly-1')
        with self.assertRaises(ValueError):
            check_resume(dict(resume, historyPolicy=42), True)
