"""連休の検査に使う架空の勤務表。"""
from copy import deepcopy
from solver.tests.test_overtime_fairness import overtime_fixture


def reduction_fixture(locked=False):
    raw, rows = overtime_fixture()
    raw['dailyRequiredStaff'] = {str(d): [0, 1, 0] for d in range(1, 6)}
    for st in raw['staff'][:3]:
        st['canOvertime'] = False
        rows[st['id']] = {str(d): 'off' for d in range(1, 32)}
    raw['locked'] = deepcopy(rows)
    raw['staff'].append({'id': 'p', 'type': 'part', 'monthlyDaysOff': 27,
                         'startTime': '09:00', 'endTime': '17:00', 'maxDaysPerWeek': 7, 'maxConsecutive': 5})
    raw['history']['p'] = ['off'] * 7
    raw['fairnessExcludedStaff'].append('p')
    rows['p'] = {str(d): 'part' if d <= 4 else 'off' for d in range(1, 32)}
    if locked:
        raw['locked']['p'] = {str(d): 'part' if d <= 5 else 'off' for d in range(1, 32)}
    policy = {s['id']: dict(min=0, target=0, max=0, fixed=True) for s in raw['staff'][:-1]}
    policy['p'] = dict(min=25, target=27, max=27, fixed=False)
    return raw, rows, policy
