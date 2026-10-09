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
    def checked(self, p, draft=False, optimize=False, seconds=3):
        r = solve(p, seconds=seconds, optimize=optimize, allow_staffing_shortfall=draft)
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

    def test_three_staff_same_block_have_exactly_one_unmet(self):
        # 達成できる夜勤日は2日。3人同時の希望なら少なくとも1人は未達。
        # 夜勤を各4回へ配れる7人で、同日の希望だけを検査する。
        # 別項目の夜勤回数差の証明に左右されず、衝突件数の最少証明を確認する。
        p=fixture(7);p['requests']={sid:[6] for sid in ('s0','s1','s2')};p['shiftRequests']={}
        for draft in (False,True):
            r=self.checked(p,draft,seconds=5);self.assertEqual(len(r['nightRestPreferences']['unmet']),1)
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
            self.assertEqual(len(r['nightRestPreferences']['unmet']),0)

    def test_two_staff_same_request_can_both_be_met(self):
        p=fixture(4);p['requests']['s1']=[6]
        r=self.checked(p,seconds=5)
        self.assertEqual(r['nightRestPreferences']['unmet'],[])
        self.assertEqual({next(d for d in (3,4) if r['assignments'][sid][str(d)]=='night')
                          for sid in ('s0','s1')},{3,4})

    def test_both_patterns_are_equal_and_preserve_two_required_rest_blocks(self):
        for night_day in (3,4):
            p=fixture(6);p['requests']={'s0':[6,15]};p['shiftRequests']={}
            p['staff'][0]['minConsecutiveRest']=2
            p['locked']={'s0':{str(night_day):'night','7':'off','8':'early',
                              '12':'night','16':'off'}}
            r=self.checked(p,seconds=5)
            self.assertEqual(r['nightRestPreferences']['metCount'],2)
            self.assertEqual(r['nightRestPreferences']['rule'],'night-request-gap-1')
            self.assertGreaterEqual(r['consecutiveRest']['s0']['actual'],2)
            self.assertTrue(r['nightRestPreferences']['minimumUnmetProven'])
            # 検査APIでも直結・公休1日を同じ達成として再集計する。
            checked=dispatch({'input':p,'action':'validate','assignments':r['assignments']})
            self.assertEqual(checked['status'],'VALID')
            self.assertEqual(checked['nightRestPreferences']['metCount'],2)
            from solver.auto_schedule import inspect
            self.assertEqual(inspect(p,r['assignments'])['nightRestPreferences']['metCount'],2)
            fixed=deepcopy(p);fixed['locked']=deepcopy(r['assignments'])
            quota={st['id']:dict(min=9,target=9,max=9,fixed=True) for st in fixed['staff']}
            auto=dispatch({'mode':'auto','autoPhase':'adjust','input':fixed,'seconds':5,
                           'holidayPolicy':quota,'referenceAssignments':r['assignments']})
            self.assertIn(auto['status'],('FEASIBLE','OPTIMAL'),auto)
            self.assertEqual(auto['nightRestPreferences']['metCount'],2)
            self.assertEqual(auto['optimizationPolicy'],'auto-holidays-2')

    def test_spaced_pattern_supports_all_three_period_boundaries(self):
        for day,hist,locks in [
                (1,['off']*4+['night','nightOff','off'],{}),
                (2,['off']*5+['night','nightOff'],{'1':'off'}),
                (3,['off']*6+['night'],{'1':'nightOff','2':'off'})]:
            p=fixture(6);p['shiftRequests']={};p['requests']={'s0':[day,day+1]}
            p['history']['s0']=hist;p['locked']={'s0':locks}
            r=self.checked(p,seconds=5)
            self.assertEqual(r['nightRestPreferences']['requestedCount'],1)
            self.assertEqual(r['nightRestPreferences']['metCount'],1)
            self.assertEqual(p['history']['s0'],hist)

    def test_two_gap_days_are_legal_but_unmet(self):
        p=fixture(6);p['shiftRequests']={};p['requests']={'s0':[6]}
        p['locked']={'s0':{'2':'night','5':'off'}}
        r=self.checked(p,seconds=5)
        self.assertEqual(len(r['nightRestPreferences']['unmet']),1)
        self.assertTrue(r['nightRestPreferences']['minimumUnmetProven'])
        self.assertEqual(r['nightRestPreferences']['unmet'][0]['nightDays'],[4,3])

    def test_report_requires_exact_gap_off_and_recovery(self):
        from itertools import product
        p=normalize(fixture());p['requests']={'s0':[6,7]}
        for shifts in product(('night','nightOff','off','early','late'),repeat=3):
            rows={'s0':dict(zip(('3','4','5'),shifts))}
            expected=(shifts[1:]==('night','nightOff') or shifts==('night','nightOff','off'))
            self.assertEqual(report(p,rows)['metCount'],int(expected),shifts)

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
