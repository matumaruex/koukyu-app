"""上位の勤務配置の例外を改善するとき、旧表の人数不足で探索を塞がない。"""
from copy import deepcopy
import unittest
from unittest.mock import patch

from solver.allocation import metrics
from solver.engine import solve
from solver.input_data import normalize
from solver.quality_search import search
from solver.validator import validate


def arrangement_fixture(single=True):
    rows = {f's{i}': {str(d): 'off' for d in range(1, 32)} for i in range(3)}
    for d in range(1, 32):
        rows[f's{(d - 1) % 3}'][str(d)] = 'night'
        rows[f's{(d - 2) % 3}'][str(d)] = 'nightOff'
    offs = ({3, 6, 8, 11, 14, 17, 20, 23, 26, 29, 30} if single else
            {3, 6, 8, 9, 10, 11, 15, 19, 23, 27, 30})
    rows['p'] = {str(d): 'off' if d in offs else 'part' for d in range(1, 32)}
    raw = {'year': 2026, 'month': 10, 'requiredStaff': [0, 0, 0], 'maxReducedSundays': 0,
           'partWeeklyLimit': False, 'excludeNightFromConsecutive': True, 'maxConsecutiveOff': 3,
           'nightDistribution': True, 'overtimeDistribution': True, 'overtimeCycleLimit': True,
           'staff': [{'id': f's{i}', 'type': 'full', 'nightShiftType': 'all',
                      'monthlyDaysOff': 0, 'maxConsecutive': 3} for i in range(3)]
                    + [{'id': 'p', 'type': 'part', 'nightShiftType': 'none', 'monthlyDaysOff': 11,
                        'fixedDaysOff': True, 'avoidIsolatedWork': single,
                        'startTime': '09:00', 'endTime': '17:00', 'maxConsecutive': 3}],
           'history': {sid: ['off'] * 5 for sid in rows}, 'fairnessExcludedStaff': list(rows),
           'requests': {'p': [6]}, 'shiftRequests': {'p': {'24': 'part'}},
           'dailyRequiredStaff': {'7': [0, 1, 0]},
           'locked': {sid: deepcopy(row) for sid, row in rows.items() if sid != 'p'}}
    raw['history']['s2'][-1] = 'night'
    raw['locked']['p'] = ({'6': 'off', '8': 'off'} if single else
                          {d: shift for d, shift in rows['p'].items() if d not in ('7', '8')})
    return raw, rows


def matching_resume(single=True):
    return {'stage': 'placement', 'idle': 30, 'proven': {'conditions': True},
            'proofValues': {'conditions': [0]}, 'preservedCommonExtraDaysOff': 0,
            'restStreakPolicy': 'requested-off-max3-1',
            **({'isolatedWorkPolicy': 'off-work-off-1'} if single else {}),
            'historyPolicy': 'five-day-no-weekly-1', 'nightConsecutivePolicy': 'exclude-night-1',
            'nightDistributionPolicy': 'rolling-night-distribution-1',
            'overtimeDistributionPolicy': 'rolling-overtime-distribution-1'}


class ImprovementArrangementScopeTests(unittest.TestCase):
    def assert_improves(self, single, resume=None):
        raw, before = arrangement_fixture(single)
        original = deepcopy((raw, before))
        options = dict(seconds=4, quality_first=True, allow_staffing_shortfall=True,
                       allow_rule_exceptions=True)
        fresh = solve(raw, **options)
        self.assertIn('assignments', fresh, fresh)
        self.assertEqual(fresh['staffingShortfallTotal'], 1)
        with patch('solver.engine.quality_search', wraps=search) as invoked:
            result = solve(raw, initial_assignments=before, resume=resume, **options)
        self.assertIn('assignments', result, result)
        self.assertEqual(result['staffingShortfallTotal'], 1)
        for field in ('isolatedWorkExceptions', 'restStreakExceptions'):
            self.assertEqual(result.get(field, 0), fresh.get(field, 0))
        self.assertEqual(result['assignments']['p']['6'], 'off')
        self.assertEqual(result['assignments']['p']['24'], 'part')
        self.assertEqual(list(result['assignments']['p'].values()).count('off'), 11)
        self.assertFalse([e for e in validate(raw, result['assignments'])
                          if e['code'] not in ('rest_streak', 'coverage')])
        self.assertEqual(result['allocation']['before'], metrics(normalize(raw), before))
        self.assertTrue(result['improved'])
        self.assertEqual((raw, before), original)
        self.assertIsNone(invoked.call_args.kwargs['resume'])
        self.assertNotEqual(invoked.call_args.kwargs['initial_assignments'], before)

    def test_single_work_repair_can_increase_lower_priority_shortage(self):
        self.assert_improves(True)

    def test_rest_streak_repair_can_increase_lower_priority_shortage(self):
        self.assert_improves(False)

    def test_repaired_candidate_restarts_old_placement_proof(self):
        self.assert_improves(True, matching_resume())

    def test_timeout_after_repair_keeps_repaired_table_and_original_comparison(self):
        raw, before = arrangement_fixture()
        def stop_search(*args, **kwargs):
            return search(*args, **dict(kwargs, seconds=.000001))
        with patch('solver.engine.quality_search', side_effect=stop_search):
            result = solve(raw, seconds=4, quality_first=True, initial_assignments=before,
                           allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(result.get('isolatedWorkExceptions', 0), 0)
        self.assertEqual(result['staffingShortfallTotal'], 1)
        self.assertTrue(result['improved'])
        self.assertFalse(result.get('previousKept', False))
        self.assertEqual(result['allocation']['before'], metrics(normalize(raw), before))

    def test_already_minimal_initial_keeps_existing_search_scope(self):
        raw, _ = arrangement_fixture()
        options = dict(seconds=4, quality_first=True, allow_staffing_shortfall=True,
                       allow_rule_exceptions=True)
        fresh = solve(raw, **options)
        before = deepcopy(fresh['assignments'])
        resume = dict(matching_resume(), stage='conditions', idle=0, proven={}, proofValues={})
        with patch('solver.engine.quality_search', wraps=search) as invoked:
            result = solve(raw, initial_assignments=before, resume=resume, **options)
        self.assertIn('assignments', result, result)
        self.assertEqual(invoked.call_args.kwargs['initial_assignments'], before)
        self.assertEqual(invoked.call_args.kwargs['resume'], resume)
        self.assertLessEqual(result['staffingShortfallTotal'], fresh['staffingShortfallTotal'])

    def test_single_call_improvement_uses_the_same_repaired_candidate(self):
        raw, before = arrangement_fixture()
        result = solve(raw, seconds=4, initial_assignments=before,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertIn('assignments', result, result)
        self.assertEqual(result.get('isolatedWorkExceptions', 0), 0)
        self.assertEqual(result['staffingShortfallTotal'], 1)
        self.assertEqual(result['allocation']['before'], metrics(normalize(raw), before))
        self.assertTrue(result['improved'])


if __name__ == '__main__':
    unittest.main()
