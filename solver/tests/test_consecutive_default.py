"""未指定の3日、明示指定、前期・＋1を実際の計算と独立検査で確認する。"""
import unittest
from solver.engine import solve
from solver.validator import validate


def fixture(run=3, limit=0, staff_type='part', night='none'):
    st={'id':'s0','type':staff_type,'nightShiftType':night,'monthlyDaysOff':0,
        'maxConsecutive':limit,'maxDaysPerWeek':7,'startTime':'09:00','endTime':'17:00'}
    shift='part' if staff_type=='part' else 'early'
    row={str(d):shift if d<=run else 'off' for d in range(1,29)}
    return {'year':2026,'month':2,'staff':[st],'requiredStaff':[0,0,0],
            'maxReducedSundays':0,'locked':{'s0':row},'history':{'s0':['off']*7}}, {'s0':row}


class ConsecutiveDefaultTests(unittest.TestCase):
    def test_unspecified_is_three_for_all_staff_types(self):
        for kind,night in [('part','none'),('full','none'),('full','all'),('full','weekday')]:
            for omitted in (False,True):
                with self.subTest(kind=kind,night=night,omitted=omitted):
                    raw,rows=fixture(3,staff_type=kind,night=night)
                    if omitted: del raw['staff'][0]['maxConsecutive']
                    self.assertFalse([e for e in validate(raw,rows) if e['code']=='consecutive'])
                    rows['s0']['4']='part' if kind=='part' else 'early'
                    errors=[e for e in validate(raw,rows) if e['code']=='consecutive']
                    self.assertEqual([(e['day'],e['limit']) for e in errors],[(4,3)])

    def test_engine_allows_three_and_rejects_four(self):
        for run,expected in [(3,'DRAFT'),(4,'INFEASIBLE')]:
            raw,rows=fixture(run)
            result=solve(raw,seconds=3,allow_night_shortfall=True,allow_staffing_shortfall=True)
            if expected=='DRAFT':
                self.assertIn(result['status'],('DRAFT','FEASIBLE','OPTIMAL'))
                self.assertEqual(result['assignments'],rows)
                self.assertFalse([e for e in validate(raw,result['assignments']) if e['code']=='consecutive'])
            else: self.assertEqual(result['status'],expected)

    def test_explicit_limit_and_plus_one_are_preserved(self):
        for limit,plus,run,allowed in [(2,False,3,False),(5,False,4,True),(0,True,4,True),(0,True,5,False)]:
            raw,rows=fixture(run,limit)
            raw['staff'][0]['allowConsecutivePlus1']=plus
            errors=[e for e in validate(raw,rows) if e['code'] in ('consecutive','consecutive_plus_one')]
            self.assertEqual(not errors,allowed)
            result=solve(raw,seconds=3,allow_night_shortfall=True,allow_staffing_shortfall=True)
            self.assertEqual(result['status']=='INFEASIBLE',not allowed)

    def test_previous_period_counts_and_recovery_breaks_run(self):
        raw,rows=fixture(2)
        raw['history']['s0'][-2:]=['part','part']
        self.assertEqual([e['day'] for e in validate(raw,rows) if e['code']=='consecutive'],[2])
        raw['history']['s0'][-1]='nightOff'
        self.assertFalse([e for e in validate(raw,rows) if e['code']=='consecutive'])
