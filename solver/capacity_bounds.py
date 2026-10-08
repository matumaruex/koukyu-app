"""制約を緩めた供給上限から計算する安全な下限。届かない候補を不可能とは呼ばない。"""
from datetime import timedelta
from itertools import combinations
from math import ceil
from .allocation import CHECKPOINTS, covers
from .input_data import normalize


def domains(p, st, day):
    sid = st['id']
    dt = p['start'] + timedelta(days=day - 1)
    if st['type'] == 'part':
        allowed = {'off', 'part'}
    else:
        allowed = {'off', 'nightOff'}
        if st['dayShiftType'] != 'late' or st['dayShiftFlexible']:
            allowed.add('early')
        if st['dayShiftType'] != 'early' or st['dayShiftFlexible']:
            allowed.add('late')
        if st['canOvertime']:
            allowed.add('overtime')
        if st['nightShiftType'] == 'all' or (st['nightShiftType'] == 'weekday' and dt.weekday() < 4):
            allowed.add('night')
    wishes = p['shiftRequests'].get(sid, {})
    locked = p['locked'].get(sid, {})
    def fixed(d):
        if d <= 0:
            return p['history'][sid][d + 6]
        if d in p['requests'].get(sid, []):
            return 'off'
        return locked.get(d, wishes.get(d))
    specified = [v for v in (wishes.get(day), locked.get(day), 'off' if day in p['requests'].get(sid, []) else None) if v]
    if fixed(day - 1) == 'night':
        specified.append('nightOff')
    if fixed(day - 1) == 'nightOff' or fixed(day - 2) == 'night':
        specified.append('off')
    for value in specified:
        allowed &= {value}
    if day == 1 and fixed(0) != 'night':
        allowed.discard('nightOff')
    elif day > 1:
        previous = p['start'] + timedelta(days=day - 2)
        if st['type'] == 'part' or st['nightShiftType'] == 'none' or (st['nightShiftType'] == 'weekday' and previous.weekday() >= 4):
            allowed.discard('nightOff')
    return allowed


def shortage_bounds(raw):
    """日別に夜勤・明けを一人ずつ確保した場合の配置可能人数の上限。

    連勤・週上限・公休総数などは緩めるので、ここで得た不足は公休を減らしても残る。
    各時刻を独立に最大化し、日曜も最も都合よく緩和する（下限を過大にしない）。
    """
    p = normalize(raw)
    entries = []
    for day in range(1, p['days'] + 1):
        choices = [domains(p, st, day) for st in p['staff']]
        night = [i for i, k in enumerate(choices) if 'night' in k]
        recovery_count = sum(p['history'][st['id']][-1] == 'night' for st in p['staff']) if day == 1 else 1
        recovery = [i for i, k in enumerate(choices) if 'nightOff' in k]
        maxima = [0, 0, 0]
        possible = False
        for ni in night:
            for rec in combinations(recovery, recovery_count):
                if ni in rec:
                    continue
                remaining = [k - {'night', 'nightOff'} for i, k in enumerate(choices) if i != ni and i not in rec]
                if any(not k for k in remaining):
                    continue
                possible = True
                for j, t in enumerate(CHECKPOINTS):
                    count = int(covers(p['staff'][ni], 'night', t))
                    count += sum(covers(p['staff'][i], 'nightOff', t) for i in rec)
                    count += sum(any(covers(st, k, t) for k in choices[i] - {'night', 'nightOff'})
                                 for i, st in enumerate(p['staff']) if i != ni and i not in rec)
                    maxima[j] = max(maxima[j], count)
        # 不成立の局所モデルは別途全体で証明する。人数不足の証明には流用しない。
        if not possible:
            return {'total': 0, 'byCheckpoint': [0, 0, 0], 'days': [], 'localConflict': True}
        needs = p['dailyRequiredStaff'].get(day, p['requiredStaff'])
        misses = [max(0, need - maximum) for need, maximum in zip(needs, maxima)]
        reducible = ((p['start'] + timedelta(days=day - 1)).weekday() == 6 and day not in p['dailyRequiredStaff'])
        entries.append({'day': day, 'missing': misses, 'reducible': reducible})
    points = []
    for j in range(3):
        benefit = sorted((int(e['missing'][j] > 0) for e in entries if e['reducible'] and j < 2), reverse=True)
        points.append(sum(e['missing'][j] for e in entries) - sum(benefit[:p['maxReducedSundays']]))
    return {'total': sum(points), 'byCheckpoint': points,
            'days': [{'day': e['day'], 'missing': [max(0, v - int(e['reducible'] and j < 2 and p['maxReducedSundays'] > 0))
                                               for j, v in enumerate(e['missing'])]} for e in entries if any(e['missing'])]}


def overtime_bound(raw, shortage, *, actual_off=None, bounds=None):
    """時刻の組ごとの需要下限−非残業勤務の供給上限。

    パートが朝夕の両方を覆う場合も対応。任意の日別必要人数・希望休・日曜緩和を再計算する。
    actual_offを渡した証明は、その確保済みの実際の休みを維持する範囲に限定する。
    """
    p = normalize(raw)
    bounds = bounds or shortage_bounds(raw)
    best = 0
    for pair in combinations(range(3), 2):
        demand, reductions = 0, []
        for day in range(1, p['days'] + 1):
            needs = p['dailyRequiredStaff'].get(day, p['requiredStaff'])
            demand += sum(needs[j] for j in pair)
            if (p['start'] + timedelta(days=day - 1)).weekday() == 6 and day not in p['dailyRequiredStaff']:
                reductions.append(sum(int(j < 2 and needs[j] > 0) for j in pair))
        demand -= sum(sorted(reductions, reverse=True)[:p['maxReducedSundays']])
        # 別の時刻で必ず残る不足には、許容した不足の予算を先に使う。
        available_shortage = max(0, shortage - sum(bounds['byCheckpoint'][j] for j in range(3) if j not in pair))
        supply, gain = 0, 0
        for st in p['staff']:
            sid = st['id']
            ordinary = ('part',) if st['type'] == 'part' else ('early', 'late', 'night', 'nightOff')
            capacity = max(sum(covers(st, k, CHECKPOINTS[j]) for j in pair) for k in ordinary)
            off = max(st['monthlyDaysOff'], len(set(p['requests'].get(sid, []))), (actual_off or {}).get(sid, 0))
            supply += (p['days'] - off) * capacity
            if st['type'] != 'part' and st['canOvertime']:
                gain = max(gain, sum(covers(st, 'overtime', CHECKPOINTS[j]) for j in pair) - capacity)
        deficit = max(0, demand - available_shortage - supply)
        if gain > 0:
            best = max(best, ceil(deficit / gain))
    return best
