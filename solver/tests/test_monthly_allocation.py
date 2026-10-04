"""月を跨ぐ配置の交換、残業の優先順位、前の表と証明の扱いを検査する。"""
import unittest
from copy import deepcopy
from solver.allocation import metrics, weights, POLICY
from solver.engine import solve, quality_value
from solver.input_data import normalize
from solver.validator import validate


def exchange_fixture():
    # 4日目のA残は、その日の通常勤務への変更だけでは消せない。
    # 8日目の余剰配置と勤務を交換すれば、公休数を変えずに消せる。
    n, k = 28, 17
    a = {f's{i}': {str(d): 'off' for d in range(1, n+1)} for i in range(k)}
    history = {sid: ['off'] * 7 for sid in a}
    history['s16'][-1] = 'night'
    for d in range(1, n+1):
        a[f's{4+(d-1)%13}'][str(d)] = 'night'
        a[f's{4+(d-2)%13}'][str(d)] = 'nightOff'
    a['s0'].update({'4':'overtime', '8':'early'})
    a['s1']['8'] = 'late'
    a['s2']['8'] = 'early'
    a['s3']['4'] = 'early'
    staff = [{'id': sid, 'type':'full', 'monthlyDaysOff': list(row.values()).count('off'),
              'nightShiftType':'none' if i < 4 else 'all', 'maxConsecutive':5,
              'canOvertime':i == 0,
              'dayShiftType':'late' if i == 1 else 'early' if i in (2,3) else 'both'}
             for i,(sid,row) in enumerate(a.items())]
    locked = {sid:{d:v for d,v in row.items() if sid not in ('s0','s1','s2') or d not in ('4','8')}
              for sid,row in a.items()}
    p = {'year':2026, 'month':2, 'staff':staff, 'history':history, 'locked':locked,
         'maxExtraOffSpread':0, 'requiredStaff':[0,0,0], 'maxReducedSundays':0,
         'dailyRequiredStaff':{'4':[3,2,2], '8':[2,2,2]}}
    assert validate(p, a) == []
    return p, a


class MonthlyAllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.before = exchange_fixture()
        cls.result = solve(cls.raw, seconds=5, initial_assignments=cls.before)
        assert cls.result['status'] == 'OPTIMAL', cls.result

    def test_overtime_requires_monthly_exchange_and_can_be_removed(self):
        for shift in ('early','late','off'):
            local = deepcopy(self.before)
            local['s0']['4'] = shift
            self.assertTrue(any(e['code']=='coverage' for e in validate(self.raw,local)))
        r = self.result
        self.assertEqual(r['allocation']['overtimeTotal'],0)
        self.assertEqual(r['allocation']['overtimeReducedBy'],1)
        self.assertLess(r['allocation']['surplusTotal'],r['allocation']['before']['surplusTotal'])
        self.assertEqual(validate(self.raw,r['assignments']),[])
        for sid,row in self.before.items():
            self.assertEqual(list(row.values()).count('off'),list(r['assignments'][sid].values()).count('off'))
        self.assertEqual(r['allocation']['before']['overtimeTotal'],1)
        self.assertEqual(r['optimizationPolicy'],POLICY)
        self.assertTrue(r['allocation']['minimumOvertimeProven'])

    def test_model_objective_and_completed_table_score_match(self):
        r = self.result
        self.assertEqual(r['objective'],quality_value(normalize(self.raw),r['assignments']))
        self.assertEqual(r['bestBound'],r['objective'])
        self.assertTrue(r['improved'])

    def test_hard_overtime_request_is_kept(self):
        p = deepcopy(self.raw)
        p['shiftRequests'] = {'s0':{'4':'overtime'}}
        r = solve(p,seconds=5,initial_assignments=self.before)
        self.assertEqual(r['status'],'OPTIMAL')
        self.assertEqual(r['assignments']['s0']['4'],'overtime')
        self.assertEqual(r['allocation']['overtimeTotal'],1)
        self.assertEqual(validate(p,r['assignments']),[])

    def test_timeout_keeps_previous_without_claiming_minimum(self):
        r = solve(self.raw,seconds=0.000001,initial_assignments=self.before)
        self.assertEqual(r['assignments'],self.before)
        self.assertTrue(r['previousKept'])
        self.assertFalse(r['allocation']['minimumOvertimeProven'])

    def test_full_round_of_existing_extra_holidays_is_preserved(self):
        p = deepcopy(self.raw)
        for st in p['staff']:
            st['monthlyDaysOff'] -= 1
        r = solve(p,seconds=5,initial_assignments=self.before)
        self.assertEqual(r['status'],'OPTIMAL')
        self.assertGreaterEqual(r['allocation']['commonExtraDaysOff'],1)
        self.assertEqual(r['allocation']['preservedCommonExtraDaysOff'],1)

    def test_overtime_reduction_beats_all_lower_priority_changes(self):
        p = normalize(self.raw)
        w, _ = weights(p)
        self.assertGreater(w[0],sum(bound*weight for bound,weight in
            zip((3*len(p['staff'])*p['days'],6,p['days'],weights(p)[0][-2]-1),w[1:])))
        # A/Bを揃えるためだけにA残へ変更すると評価は悪化する。
        worse = deepcopy(self.result['assignments'])
        worse['s0']['8'] = 'overtime'
        self.assertGreater(quality_value(p,worse),quality_value(p,self.result['assignments']))

    def test_overtime_spread_excludes_staff_not_allowed_to_work_overtime(self):
        p = normalize(self.raw)
        m = metrics(p,self.before)
        self.assertEqual(m['overtimeByStaff'],{'s0':1})
        self.assertEqual(m['overtimeSpread'],0)

    def test_same_overtime_total_and_surplus_favor_shared_overtime(self):
        p = deepcopy(self.raw)
        p['staff'][1]['canOvertime'] = True
        concentrated = deepcopy(self.before)
        concentrated['s0']['8'] = 'overtime'
        shared = deepcopy(self.before)
        shared['s1']['8'] = 'overtime'
        self.assertEqual(validate(p,concentrated),[])
        self.assertEqual(validate(p,shared),[])
        normalized = normalize(p)
        left,right = metrics(normalized,concentrated),metrics(normalized,shared)
        self.assertEqual(left['overtimeTotal'],right['overtimeTotal'])
        self.assertEqual(left['surplusTotal'],right['surplusTotal'])
        self.assertEqual((left['overtimeSpread'],right['overtimeSpread']),(2,0))
        self.assertLess(quality_value(normalized,shared),quality_value(normalized,concentrated))

    def test_required_work_can_exceed_needed_staff_without_becoming_impossible(self):
        p = deepcopy(self.raw)
        p['shiftRequests'] = {'s0':{'8':'early'},'s1':{'8':'late'},'s2':{'8':'early'}}
        r = solve(p,seconds=5,initial_assignments=self.before)
        self.assertEqual(r['status'],'OPTIMAL')
        self.assertEqual(validate(p,r['assignments']),[])
        self.assertEqual(r['allocation']['overtimeTotal'],1)
        self.assertEqual([r['assignments'][sid]['8'] for sid in ('s0','s1','s2')],['early','late','early'])

    def test_every_supported_size_fits_integer_objective_bounds(self):
        for n in (28,29,30,31):
            for k in range(1,41):
                _, shortage_weight = weights({'days':n,'staff':[{}]*k})
                self.assertLess(shortage_weight*(3*n*40+1),2**63-1)

    def test_large_input_model_is_valid_not_integer_overflow(self):
        from solver.tests.test_night_rest import roomy_fixture
        p = roomy_fixture()
        p['month'] = 10
        p['staff'] = [dict(p['staff'][0],id=f's{i}') for i in range(40)]
        p['history'] = {st['id']:['off']*7 for st in p['staff']}
        r = solve(p,seconds=0.000001,allow_staffing_shortfall=True)
        self.assertEqual(r['status'],'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
