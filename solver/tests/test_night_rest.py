"""Mandatory recovery holidays, manual-edit detection, and period-boundary carry-over."""
import unittest
from copy import deepcopy
from solver.engine import solve
from solver.validator import validate
from solver.service import dispatch


def roomy_fixture():
    return {'year':2026,'month':2,'maxExtraOffSpread':1,'staff':[
        {'id':f's{i}','type':'full','monthlyDaysOff':9,'nightShiftType':'all',
         'canOvertime':True,'maxConsecutive':5} for i in range(16)
    ],'history':{f's{i}':['off']*7 for i in range(16)}}


class NightRestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=roomy_fixture()
        cls.raw['locked']={'s0':{'3':'night','28':'night'},'s1':{'27':'night'}}
        cls.result=solve(cls.raw,seconds=10,optimize=False)
        assert cls.result['status'] in ('FEASIBLE','OPTIMAL'),cls.result
        cls.table=cls.result['assignments']

    def test_generated_and_locked_night_requires_two_following_days(self):
        self.assertEqual([self.table['s0'][str(d)] for d in (3,4,5)],['night','nightOff','off'])
        for row in self.table.values():
            for day in range(2,29):
                if row[str(day-1)]=='nightOff':
                    self.assertEqual(row[str(day)],'off')
        self.assertEqual(validate(self.raw,self.table),[])

    def test_previous_night_off_requires_first_day_holiday(self):
        p=roomy_fixture();p['history']['s0'][-2:]=['night','nightOff']
        r=solve(p,seconds=10,optimize=False)
        self.assertIn(r['status'],('FEASIBLE','OPTIMAL'))
        self.assertEqual(r['assignments']['s0']['1'],'off')
        self.assertEqual(validate(p,r['assignments']),[])

    def test_previous_night_requires_recovery_then_holiday(self):
        p=roomy_fixture();p['history']['s0'][-1]='night'
        r=solve(p,seconds=10,optimize=False)
        self.assertIn(r['status'],('FEASIBLE','OPTIMAL'))
        self.assertEqual([r['assignments']['s0'][str(d)] for d in (1,2)],['nightOff','off'])
        self.assertEqual(validate(p,r['assignments']),[])

    def test_work_locked_after_recovery_is_proven_impossible(self):
        p=roomy_fixture();p['locked']={'s0':{'3':'night','5':'early'}}
        self.assertEqual(solve(p,seconds=5)['status'],'INFEASIBLE')
        p=roomy_fixture();p['history']['s0'][-2:]=['night','nightOff'];p['locked']={'s0':{'1':'early'}}
        self.assertEqual(solve(p,seconds=5)['status'],'INFEASIBLE')
        p=roomy_fixture();p['history']['s0'][-1]='night';p['locked']={'s0':{'2':'late'}}
        self.assertEqual(solve(p,seconds=5)['status'],'INFEASIBLE')

    def test_validator_detects_manual_and_imported_work_after_recovery(self):
        a=deepcopy(self.table);a['s0']['5']='early'
        errors=validate(self.raw,a)
        self.assertTrue(any(e['code']=='night_rest' and e['staff']=='s0' and e['day']==5 for e in errors))
        r=dispatch({'action':'validate','input':self.raw,'assignments':a})
        self.assertEqual(r['status'],'INVALID')
        self.assertTrue(any(e['code']=='night_rest' for e in r['validationErrors']))
        p=deepcopy(self.raw);p['history']['s0'][-2:]=['night','nightOff'];a=deepcopy(self.table);a['s0']['1']='early'
        self.assertTrue(any(e['code']=='night_rest' and e['day']==1 for e in validate(p,a)))

    def test_carry_forward_includes_recovery_holiday(self):
        self.assertEqual(self.result['carryForward']['s0']['nextDay'],'nightOff')
        self.assertEqual(self.result['carryForward']['s0']['nextDays'],['nightOff','off'])
        self.assertEqual(self.result['carryForward']['s1']['nextDay'],'off')
        self.assertEqual(self.result['carryForward']['s1']['nextDays'],['off'])

    def test_night_coverage_remains_required_even_when_holidays_conflict(self):
        p=roomy_fixture()
        for st in p['staff'][2:]:st['nightShiftType']='none'
        self.assertEqual(solve(p,seconds=5)['status'],'INFEASIBLE')


if __name__=='__main__':unittest.main()
