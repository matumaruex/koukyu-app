"""3連休の基本ルール：希望休の例外・境界・最少証明・既存ルールとの優先順位。"""
import unittest
from unittest.mock import patch, MagicMock
from ortools.sat.python import cp_model
from solver.service import dispatch, check_resume
from solver.input_data import normalize
from solver.validator import validate
from solver.rest_streak import ranges, count, POLICY
from solver.tests.test_night_fairness import six_staff

SCREEN = dict(seconds=8, qualityFirst=True, allowStaffingShortfall=True, allowRuleExceptions=True)


def setting(**fields):
    raw = six_staff()
    raw.update(excludeNightFromConsecutive=True, partWeeklyLimit=False, maxConsecutiveOff=3)
    raw['staff'][0].update({'nightShiftType': 'none', 'fixedDaysOff': True, **fields})
    return raw


class RestStreakTests(unittest.TestCase):
    def test_optional_api_and_strict_type(self):
        self.assertIsNone(normalize(six_staff())['maxConsecutiveOff'])
        for value in (0, 2, 4, True, 3.0, '3'):
            raw = setting();raw['maxConsecutiveOff'] = value
            with self.assertRaises(ValueError):
                normalize(raw)
        self.assertEqual(check_resume({'stage':'conditions','restStreakPolicy':POLICY}, True)['restStreakPolicy'], POLICY)
        with self.assertRaises(ValueError):
            check_resume({'stage':'conditions','restStreakPolicy':3}, True)

    def test_free_off_windows_and_night_off_breaks_run(self):
        p = normalize(setting())
        row = {str(d):'early' for d in range(1,31)}
        for d in (5,6,7,8,9,12,13,15,16,17):row[str(d)]='off'
        row['14']='nightOff'
        self.assertEqual(ranges(p,p['staff'][0],row),[{'start':5,'end':9,'count':2}])
        p['maxConsecutiveOff']=None
        self.assertEqual(ranges(p,p['staff'][0],row),[])

    def test_only_requested_days_are_exempt_not_automatic_extensions_or_locked_off(self):
        raw=setting();raw['requests']={'s0':[5,6,7,8,9]}
        row={str(d):'early' for d in range(1,31)}
        for d in range(5,10):row[str(d)]='off'
        p=normalize(raw)
        self.assertEqual(ranges(p,p['staff'][0],row),[])
        row['4']='off';row['10']='off'
        self.assertEqual(ranges(p,p['staff'][0],row),[{'start':4,'end':7,'count':1},{'start':7,'end':10,'count':1}])
        raw['requests']={};raw['locked']={'s0':{'5':'off','6':'off','7':'off','8':'off','9':'off'}}
        p=normalize(raw)
        self.assertEqual(sum(b['count'] for b in ranges(p,p['staff'][0],row)),4)

    def test_known_history_counts_but_requested_current_days_are_protected(self):
        raw=setting();row={str(d):'early' for d in range(1,31)};row['1']='off'
        p=normalize(raw)
        self.assertEqual(ranges(p,p['staff'][0],row),[{'start':-2,'end':1,'count':1}])
        del raw['history']['s0'];p=normalize(raw)
        self.assertEqual(ranges(p,p['staff'][0],row),[])
        raw['history']['s0']=['off']*5;raw['requests']={'s0':[1]};p=normalize(raw)
        self.assertEqual(ranges(p,p['staff'][0],row),[])

    def test_zero_exceptions_when_possible_and_off_quota_is_kept(self):
        raw=setting();r=dispatch(dict(SCREEN,input=raw))
        self.assertIn('assignments',r);self.assertEqual(r['restStreak']['minimum'],0)
        self.assertTrue(r['restStreak']['proven']);self.assertEqual(count(normalize(raw),r['assignments']),0)
        self.assertEqual(list(r['assignments']['s0'].values()).count('off'),9)
        self.assertEqual(validate(raw,r['assignments']),[])

    def test_five_requested_days_are_kept_without_automatic_extension(self):
        raw=setting(monthlyDaysOff=11);raw['requests']={'s0':list(range(10,15))}
        r=dispatch(dict(SCREEN,input=raw));self.assertIn('assignments',r)
        self.assertEqual(r['restStreak']['minimum'],0)
        self.assertTrue(all(r['assignments']['s0'][str(d)]=='off' for d in range(10,15)))
        self.assertNotEqual(r['assignments']['s0']['9'],'off');self.assertNotEqual(r['assignments']['s0']['15'],'off')

    def test_locked_extension_is_unavoidable_and_is_reported(self):
        raw=setting(monthlyDaysOff=11);raw['requests']={'s0':[10,11,12,13]};raw['locked']={'s0':{'9':'off'}}
        r=dispatch(dict(SCREEN,input=raw));self.assertIn('assignments',r)
        self.assertEqual(r['restStreak']['minimum'],1);self.assertEqual(r['restStreakExceptions'],1)
        self.assertTrue(all(r['assignments']['s0'][str(d)]=='off' for d in range(9,14)))
        self.assertTrue(any(e['code']=='rest_streak' for e in r['ruleExceptions']))
        self.assertEqual(r.get('exceptionCount',0),0)
        strict=dispatch({'input':raw,'seconds':3})
        self.assertEqual(strict['status'],'INFEASIBLE');self.assertNotIn('assignments',strict)

    def test_all_off_fixed_quota_has_proven_minimum_including_boundary(self):
        raw=setting(monthlyDaysOff=30)
        r=dispatch(dict(SCREEN,input=raw));self.assertIn('assignments',r)
        self.assertEqual(r['restStreak']['minimum'],30);self.assertEqual(r['restStreakExceptions'],30)
        self.assertTrue(r['restStreak']['proven']);self.assertEqual(list(r['assignments']['s0'].values()).count('off'),30)
        self.assertFalse([e for e in validate(raw,r['assignments']) if e['code']!='rest_streak'])

    def test_all_requested_off_is_exempt_even_with_old_off_history(self):
        raw=setting(monthlyDaysOff=30);raw['requests']={'s0':list(range(1,31))}
        r=dispatch(dict(SCREEN,input=raw));self.assertIn('assignments',r)
        self.assertEqual(r['restStreak']['minimum'],0);self.assertNotIn('restStreakExceptions',r)

    def test_single_work_rule_is_preserved_before_rest_cap(self):
        raw=setting(monthlyDaysOff=22,avoidIsolatedWork=True)
        r=dispatch(dict(SCREEN,input=raw));self.assertIn('assignments',r)
        self.assertEqual(r['isolatedWork']['minimum'],0)
        self.assertEqual(r['restStreak']['minimum'],10)
        self.assertEqual(r.get('exceptionCount',0),0)
        self.assertTrue(r['restStreak']['proven'])

    def test_part_time_and_required_rest_blocks(self):
        raw=setting(type='part',startTime='09:00',endTime='17:00',minConsecutiveRest=2)
        r=dispatch(dict(SCREEN,input=raw));self.assertIn('assignments',r)
        self.assertEqual(r['restStreak']['minimum'],0);self.assertEqual(validate(raw,r['assignments']),[])

    def test_unproven_positive_and_timeout_do_not_return_a_table(self):
        proof=MagicMock();proof.solve.return_value=cp_model.FEASIBLE;proof.objective_value=1;proof.wall_time=.01
        with patch('solver.engine.cp_model.CpSolver',return_value=proof):
            r=dispatch(dict(SCREEN,input=setting()))
        self.assertEqual(r['status'],'UNKNOWN');self.assertNotIn('assignments',r)
        self.assertEqual(r['search']['reason'],'rest_streak_unconfirmed')
        with patch('solver.engine.REST_STREAK_PROOF_SECONDS',.000001):
            r=dispatch(dict(SCREEN,input=setting()))
        self.assertEqual(r['status'],'UNKNOWN');self.assertNotIn('assignments',r)

    def test_manual_validation_does_not_claim_proof_and_old_resume_is_reset(self):
        raw=setting()
        rows={st['id']:{str(d):'off' for d in range(1,31)} for st in raw['staff']}
        r=dispatch({'action':'validate','input':raw,'assignments':rows})
        self.assertFalse(r['restStreak']['proven']);self.assertGreater(r['restStreak']['count'],0)
        from solver.quality_search import search
        with patch('solver.engine.quality_search',wraps=search) as wrapped:
            dispatch(dict(SCREEN,input=raw,resume={'stage':'placement','idle':30,'proven':{'conditions':True},'proofValues':{'conditions':[0]}}))
        self.assertEqual(wrapped.call_args.kwargs['resume']['stage'],'conditions')
        self.assertEqual(wrapped.call_args.kwargs['resume']['proven'],{})

    def test_large_combined_model_is_valid(self):
        raw=setting(avoidIsolatedWork=True)
        raw['staff']=[dict(raw['staff'][0],id=f's{i}',nightShiftType='all') for i in range(40)]
        raw['history']={}
        original=cp_model.CpSolver.solve
        def check(solver,model):
            self.assertEqual(model.validate(),'');solver.parameters.max_time_in_seconds=.000001
            return original(solver,model)
        with patch.object(cp_model.CpSolver,'solve',new=check):
            r=dispatch(dict(SCREEN,input=raw))
        self.assertEqual(r['status'],'UNKNOWN')

if __name__=='__main__':unittest.main()
