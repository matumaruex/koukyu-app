"""逆算した夜勤は優先希望。実際の夜勤後の休みや他の希望は必須。"""
import unittest
from copy import deepcopy
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.service import dispatch
from solver.night_preferences import report
from solver.tests.test_night_rest import roomy_fixture
from solver.tests.test_monthly_allocation import exchange_fixture

def fixture(staff_count=16):
    p = roomy_fixture(); p['requiredStaff'] = [0, 0, 0]
    p['staff'] = p['staff'][:staff_count]
    p['history'] = {st['id']: p['history'][st['id']] for st in p['staff']}
    p['requests'] = {'s0': [6, 7, 8, 15, 28]}
    p['shiftRequests'] = {'s0': {'1': 'early', '2': 'late', '3': 'overtime'}}
    return p

class RequestedNightRestTests(unittest.TestCase):
    def checked(self, p, draft=False, optimize=False):
        r = solve(p, seconds=3, optimize=optimize, allow_staffing_shortfall=draft)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE', 'DRAFT'), r)
        errors=validate(p,r['assignments'])
        self.assertTrue(all(e['code'] in ('coverage','sunday_limit') for e in errors))
        if not draft: self.assertEqual(errors,[])
        self.assertEqual(report(normalize(p),r['assignments'])['unmet'],r['nightRestPreferences']['unmet'])
        for sid, req in p.get('requests',{}).items():
            for d in req: self.assertEqual(r['assignments'][sid][str(d)],'off')
        return r

    def test_possible_blocks_and_contiguous_holidays_are_all_met(self):
        r=self.checked(fixture()); self.assertEqual(r['nightRestPreferences']['requestedCount'],3)
        self.assertEqual(r['nightRestPreferences']['unmet'],[])
        self.assertEqual([r['assignments']['s0'][str(d)] for d in (4,5,6,7,8)],['night','nightOff','off','off','off'])

    def test_two_staff_same_block_have_exactly_one_exception(self):
        # 希望の衝突を検証する。16人の夜勤公平性の証明が3秒で終わるかには依存しない。
        p=fixture(6);p['requests']['s1']=[6]
        for draft in (False,True):
            r=self.checked(p,draft);self.assertEqual(len(r['nightRestPreferences']['unmet']),1)
            self.assertEqual(r['nightRestPreferences']['unmet'][0]['day'],6)
            self.assertTrue(r['nightRestPreferences']['minimumUnmetProven'])

    def test_explicit_night_and_fixed_work_take_precedence(self):
        for field,row in [('shiftRequests',{'4':'early'}),('locked',{'5':'early'})]:
            p=fixture(6);p.setdefault(field,{})['s0']=row
            for draft in (False,True):
                r=self.checked(p,draft);self.assertEqual([(e['staff'],e['day']) for e in r['nightRestPreferences']['unmet']],[('s0',6)])
                for d,k in row.items():self.assertEqual(r['assignments']['s0'][d],k)
        p=fixture(6);p['shiftRequests']['s1']={'4':'night'};r=self.checked(p)
        self.assertEqual([r['assignments']['s1'][str(d)] for d in (4,5,6)],['night','nightOff','off'])
        self.assertEqual(len(r['nightRestPreferences']['unmet']),1)

    def test_close_blocks_and_unavailable_weekday_skip_only_impossible_chain(self):
        p=fixture();p['requests']['s0']=[6,8];self.assertEqual(len(self.checked(p)['nightRestPreferences']['unmet']),1)
        p=fixture();p['staff'][0]['nightShiftType']='weekday';p['requests']['s0']=[15]
        self.assertEqual(self.checked(p)['nightRestPreferences']['unmet'][0]['day'],15)
        p['staff'][0]['nightShiftType']='none';r=self.checked(p)
        self.assertEqual(r['nightRestPreferences']['requestedCount'],0)
        self.assertEqual(r['nightRestPreferences']['unmet'],[])

    def test_first_block_respects_actual_history_and_can_be_ordinary_holiday(self):
        for day,hist,expected in [(1,['off']*5+['night','nightOff'],0),(2,['off']*6+['night'],0),(1,['off']*7,1),(2,['off']*7,1)]:
            p=fixture();p['shiftRequests']={};p['requests']['s0']=list(range(day,day+3));p['history']['s0']=hist
            self.assertEqual(len(self.checked(p)['nightRestPreferences']['unmet']),expected)
            self.assertEqual(p['history']['s0'],hist)

    def test_real_night_recovery_holiday_and_direct_requests_remain_hard(self):
        p=fixture();p['shiftRequests']['s1']={'4':'night','6':'early'}
        for draft in (False,True):self.assertEqual(solve(p,seconds=2,allow_staffing_shortfall=draft)['status'],'INFEASIBLE')
        p=fixture();p['shiftRequests']['s1']={'4':'night'};p['shiftRequests']['s2']={'4':'night'}
        self.assertEqual(solve(p,seconds=2)['status'],'INFEASIBLE')

    def test_validator_reports_preferences_separately_from_violations(self):
        p=fixture();p['locked']={'s0':{'4':'early','5':'late'}};a=self.checked(p)['assignments']
        r=dispatch({'input':p,'action':'validate','assignments':a})
        self.assertEqual(r['status'],'VALID');self.assertEqual(len(r['nightRestPreferences']['unmet']),1)
        self.assertNotIn('minimumUnmetProven',r['nightRestPreferences'])
        a['s0']['6']='early';self.assertTrue(any(e['code']=='request' for e in validate(p,a)))

    def test_priority_keeps_necessary_overtime_to_meet_preference(self):
        p,a=exchange_fixture()
        p['locked']['s0']={d:k for d,k in a['s0'].items() if d not in ('4','5','6','8')}
        for d in ('4','5','6'):p['locked']['s7'].pop(d)
        p['staff'][7]['dayShiftType']='late'
        p['staff'][0]['nightShiftType']='all';p['staff'][1]['canOvertime']=True
        p['requests']={'s0':[6]};p['nightRestRequiredStaff']=['s0'];p['dailyRequiredStaff']={'4':[4,3,2]}
        for st in p['staff']:st['monthlyDaysOff']=0
        p['maxExtraOffSpread']=28
        r=self.checked(p,optimize=True);self.assertEqual(r['nightRestPreferences']['unmet'],[])
        self.assertGreater(r['allocation']['overtimeTotal'],0)
        # 旧設定が空でも、基本機能として同じ希望を優先する。
        p['nightRestRequiredStaff']=[];r=self.checked(p,optimize=True)
        self.assertEqual(r['nightRestPreferences']['unmet'],[])
        self.assertGreater(r['allocation']['overtimeTotal'],0)

    def test_staffing_in_draft_takes_precedence_over_night_rest_preference(self):
        p,a=exchange_fixture()
        p['locked']['s0']={d:k for d,k in a['s0'].items() if d not in ('4','5','6','8')}
        for d in ('4','5','6'):p['locked']['s7'].pop(d)
        p['staff'][7]['dayShiftType']='late';p['staff'][0]['nightShiftType']='all';p['staff'][1]['canOvertime']=True
        p['requests']={'s0':[6]};p['nightRestRequiredStaff']=['s0'];p['dailyRequiredStaff']={'4':[5,4,1]}
        for st in p['staff']:st['monthlyDaysOff']=0
        p['maxExtraOffSpread']=28
        r=self.checked(p,draft=True,optimize=True)
        self.assertEqual(validate(p,r['assignments']),[])
        self.assertEqual(len(r['nightRestPreferences']['unmet']),1)

    def test_second_phase_optimal_does_not_prove_first_phase_minimum(self):
        p=fixture();p['locked']={'s0':{'4':'early'}};a=self.checked(p)['assignments'];p['locked']=deepcopy(a)
        real_solve=cp_model.CpSolver.solve;calls=[]
        def partial(solver,model,*args,**kwargs):
            status=real_solve(solver,model,*args,**kwargs);calls.append(status)
            return cp_model.FEASIBLE if len(calls)==1 and status==cp_model.OPTIMAL else status
        with patch.object(cp_model.CpSolver,'solve',partial):r=solve(p,seconds=2)
        self.assertEqual(calls,[cp_model.OPTIMAL,cp_model.OPTIMAL])
        self.assertEqual(r['status'],'FEASIBLE')
        self.assertFalse(r['nightRestPreferences']['minimumUnmetProven'])
        self.assertFalse(r['allocation']['minimumOvertimeProven'])

    def test_many_preferences_do_not_overflow_integer_objective(self):
        p=roomy_fixture();p['month']=10;p['staff']=[dict(p['staff'][0],id=f's{i}') for i in range(40)]
        p['history']={st['id']:['off']*7 for st in p['staff']}
        p['requests']={st['id']:list(range(1,32,2)) for st in p['staff']};p['nightRestRequiredStaff']=[st['id'] for st in p['staff']]
        self.assertEqual(solve(p,seconds=0.000001,allow_staffing_shortfall=True)['status'],'UNKNOWN')

    def test_timeout_keeps_incumbent_without_claiming_minimum(self):
        p=fixture();p['locked']={'s0':{'4':'early'}};a=self.checked(p)['assignments'];p['locked']={}
        r=solve(p,seconds=0.000001,initial_assignments=a)
        self.assertEqual(r['assignments'],a);self.assertTrue(r['previousKept'])
        self.assertFalse(r['nightRestPreferences']['minimumUnmetProven']);self.assertFalse(r['allocation']['minimumOvertimeProven'])

    def test_invalid_selection_and_duplicate_ids_are_rejected(self):
        for value in [True,None,'s0',{},['unknown'],['s0','s0'],[1]]:
            p=fixture();p['nightRestRequiredStaff']=value;self.assertEqual(dispatch({'input':p})['status'],'INVALID_INPUT')
        p=fixture();self.assertEqual(normalize(p)['nightRestRequiredStaff'],[st['id'] for st in p['staff']])

    def test_legacy_selection_cannot_turn_off_other_night_staff(self):
        p=fixture();p['requests']['s1']=[6]
        for legacy in ([],['s0'],['s1']):
            p['nightRestRequiredStaff']=legacy
            r=self.checked(p)
            self.assertEqual(r['nightRestPreferences']['requestedCount'],4)
            self.assertEqual(len(r['nightRestPreferences']['unmet']),1)

    def test_part_time_and_no_night_staff_are_not_preference_targets(self):
        p=fixture();p['staff'][0]['nightShiftType']='none'
        p['staff'][1].update(type='part',nightShiftType='all',startTime='09:00',endTime='17:00',maxDaysPerWeek=3)
        p['requests']['s1']=[6]
        self.assertNotIn('s0',normalize(p)['nightRestRequiredStaff'])
        self.assertNotIn('s1',normalize(p)['nightRestRequiredStaff'])
        r=self.checked(p)
        self.assertEqual(r['nightRestPreferences']['requestedCount'],0)
        self.assertEqual(r['assignments']['s0']['6'],'off')
        self.assertEqual(r['assignments']['s1']['6'],'off')

if __name__=='__main__':unittest.main()
