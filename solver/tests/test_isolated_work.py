"""1日だけの出勤：任意の個人設定・境界・固定の尊重・最少の証明と時間切れの区別。"""
import unittest
from copy import deepcopy
from unittest.mock import patch, MagicMock
from ortools.sat.python import cp_model
from solver.service import dispatch, check_resume
from solver.input_data import normalize
from solver.validator import validate, exception_count
from solver.isolated_work import days, count, POLICY
from solver.tests.test_night_fairness import six_staff

SCREEN = dict(seconds=8, qualityFirst=True, allowStaffingShortfall=True, allowRuleExceptions=True)


def setting(**staff):
    raw = six_staff()
    raw.update(excludeNightFromConsecutive=True, partWeeklyLimit=False)
    raw['staff'][0].update({'avoidIsolatedWork': True, 'nightShiftType': 'none', 'fixedDaysOff': True, **staff})
    return raw


class IsolatedWorkTests(unittest.TestCase):
    def test_setting_is_optional_and_strictly_boolean(self):
        self.assertFalse(normalize(six_staff())['staff'][0]['avoidIsolatedWork'])
        for value in (None, 'yes', 0, 1):
            with self.assertRaises(ValueError):
                normalize(setting(avoidIsolatedWork=value))
        self.assertEqual(check_resume({'stage': 'conditions', 'isolatedWorkPolicy': POLICY}, True)['isolatedWorkPolicy'], POLICY)
        with self.assertRaises(ValueError):
            check_resume({'stage': 'conditions', 'isolatedWorkPolicy': True}, True)

    def test_actual_days_and_history_only(self):
        raw = setting()
        p = normalize(raw)
        row = {str(d): 'off' for d in range(1, 31)}
        for d, shift in [(1, 'early'), (3, 'late'), (5, 'overtime'), (7, 'part'), (10, 'early'), (11, 'late'), (14, 'nightOff'), (15, 'early'), (30, 'early')]:
            row[str(d)] = shift
        self.assertEqual(days(p, p['staff'][0], row), [1, 3, 5, 7])
        del raw['history']['s0']
        p = normalize(raw)
        self.assertEqual(days(p, p['staff'][0], row), [3, 5, 7])
        self.assertEqual(days(p, p['staff'][1], row), [])
        raw['history']['s0'] = ['early', 'off', 'off', 'off', 'early']
        row['1'] = 'off'
        p = normalize(raw)
        self.assertEqual(days(p, p['staff'][0], row), [0, 3, 5, 7])

    def test_validator_reports_the_work_day_and_marks_current_boundary(self):
        raw = setting()
        rows = {st['id']: {str(d): 'off' for d in range(1, 31)} for st in raw['staff']}
        rows['s0']['7'] = 'early'
        raw['history']['s0'] = ['off'] * 4 + ['early']
        errors = [e for e in validate(raw, rows) if e['code'] == 'isolated_work']
        self.assertEqual([(e['day'], e['workDay']) for e in errors], [(1, 0), (7, 7)])
        self.assertEqual(exception_count(normalize(raw), errors), 0)

    def test_avoids_isolated_work_and_preserves_fixed_quota(self):
        raw = setting()
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['isolatedWork']['minimum'], 0)
        self.assertTrue(r['isolatedWork']['proven'])
        self.assertEqual(count(normalize(raw), r['assignments']), 0)
        self.assertEqual(list(r['assignments']['s0'].values()).count('off'), 9)
        self.assertEqual(validate(raw, r['assignments']), [])

    def test_wishes_and_locked_shift_are_kept_as_proven_unavoidable(self):
        raw = setting()
        raw['requests'] = {'s0': [6, 8]}
        raw['locked'] = {'s0': {'7': 'early'}}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual([r['assignments']['s0'][str(d)] for d in (6, 7, 8)], ['off', 'early', 'off'])
        self.assertEqual(r['isolatedWork']['minimum'], 1)
        self.assertEqual(r['isolatedWorkExceptions'], 1)
        self.assertEqual(r['exceptionCount'], 0)
        self.assertTrue(r['isolatedWork']['proven'])
        self.assertEqual([(e['staff'], e['day']) for e in r['ruleExceptions'] if e['code'] == 'isolated_work'], [('s0', 7)])
        strict = dispatch({'input': raw, 'seconds': 3})
        self.assertEqual(strict['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', strict)

    def test_does_not_increase_higher_priority_exceptions_to_remove_singles(self):
        raw = setting(monthlyDaysOff=17, maxConsecutive=1)
        raw['fairnessExcludedStaff'] = ['s0']
        r = dispatch(dict(SCREEN, input=raw))
        # 13出勤。連勤なしなので全出勤が単独、未知の次期に続く最終日だけは判定しない。
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['isolatedWork']['minimum'], 12)
        self.assertEqual(r['isolatedWorkExceptions'], 12)
        self.assertEqual(r.get('exceptionCount', 0), 0)
        self.assertEqual(list(r['assignments']['s0'].values()).count('off'), 17)
        self.assertFalse([e for e in validate(raw, r['assignments']) if e['code'] != 'isolated_work'])

    def test_does_not_allow_singles_to_reduce_staffing_shortage(self):
        raw = setting()
        raw['requiredStaff'] = [6, 6, 6]
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn(r['status'], ('DRAFT', 'FEASIBLE', 'OPTIMAL'))
        self.assertIn('assignments', r)
        self.assertEqual(r['isolatedWork']['minimum'], 0)
        self.assertGreater(r['staffingShortfallTotal'], 0)
        self.assertFalse([e for e in validate(raw, r['assignments']) if e['code'] not in ('coverage', 'sunday_limit')])

    def test_part_time_can_opt_in_without_weekly_limit(self):
        raw = setting()
        raw['staff'][0].update(type='part', startTime='09:00', endTime='17:00', maxDaysPerWeek=1)
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn('assignments', r)
        self.assertEqual(r['isolatedWork']['minimum'], 0)
        self.assertTrue(set(r['assignments']['s0'].values()) <= {'part', 'off'})

    def test_no_consecutive_rest_keeps_priority_over_single_work(self):
        raw = setting(noConsecutiveRest=True)
        raw['requests'] = {'s0': [10, 12]}
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn('assignments', r)
        self.assertEqual(r['noConsecutiveRest']['minimum'], 0)
        self.assertEqual(r['isolatedWork']['minimum'], 1)
        self.assertEqual(r.get('restExceptionCount', 0), 0)
        self.assertEqual(r['assignments']['s0']['11'] in ('early', 'late', 'overtime'), True)

    def test_required_rest_blocks_and_balance_remain_valid(self):
        raw = setting(minConsecutiveRest=1)
        raw['staff'][1]['minConsecutiveRest'] = 1
        raw['restCountBalance'] = True
        r = dispatch(dict(SCREEN, input=raw))
        self.assertIn('assignments', r)
        self.assertEqual(r['isolatedWork']['minimum'], 0)
        self.assertEqual(r['restBalance']['excess'], 0)
        self.assertEqual(validate(raw, r['assignments']), [])

    def test_unproven_positive_minimum_is_not_accepted(self):
        proof = MagicMock()
        proof.solve.return_value = cp_model.FEASIBLE
        proof.objective_value = 1
        proof.wall_time = .01
        with patch('solver.engine.cp_model.CpSolver', return_value=proof):
            r = dispatch(dict(SCREEN, input=setting()))
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertEqual(r['search']['reason'], 'isolated_work_unconfirmed')
        self.assertNotIn('assignments', r)
        self.assertNotIn('isolatedWork', r)

    def test_time_limit_is_not_called_impossible(self):
        with patch('solver.engine.ISOLATED_PROOF_SECONDS', .000001):
            r = dispatch(dict(SCREEN, input=setting()))
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertTrue(r['search']['continueRecommended'])
        self.assertNotIn('assignments', r)

    def test_manual_validation_does_not_claim_unavoidable(self):
        raw = setting()
        rows = {st['id']: {str(d): 'off' for d in range(1, 31)} for st in raw['staff']}
        rows['s0']['7'] = 'early'
        r = dispatch({'action': 'validate', 'input': raw, 'assignments': rows})
        self.assertEqual(r['isolatedWork']['count'], 1)
        self.assertFalse(r['isolatedWork']['proven'])

    def test_old_resume_proofs_are_reset(self):
        from solver.quality_search import search
        resume = {'stage': 'placement', 'idle': 30, 'proven': {'conditions': True}, 'proofValues': {'conditions': [0]}}
        with patch('solver.engine.quality_search', wraps=search) as wrapped:
            dispatch(dict(SCREEN, input=setting(), resume=resume))
        self.assertEqual(wrapped.call_args.kwargs['resume']['stage'], 'conditions')
        self.assertEqual(wrapped.call_args.kwargs['resume']['proven'], {})

    def test_large_model_remains_within_integer_bounds(self):
        raw = setting()
        raw['staff'] = [dict(raw['staff'][0], id=f's{i}', nightShiftType='all') for i in range(40)]
        raw['history'] = {}
        original = cp_model.CpSolver.solve
        def check(solver, model):
            self.assertEqual(model.validate(), '')
            solver.parameters.max_time_in_seconds = .000001
            return original(solver, model)
        with patch.object(cp_model.CpSolver, 'solve', new=check):
            r = dispatch(dict(SCREEN, input=raw))
        self.assertEqual(r['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
