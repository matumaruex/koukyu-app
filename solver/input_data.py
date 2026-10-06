"""入力形式を検査・正規化する。シフトを組む処理は含めない。"""
from calendar import monthrange
from copy import deepcopy
from datetime import date, timedelta

SHIFTS = ('off', 'early', 'late', 'overtime', 'night', 'nightOff', 'part')


def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError('Input must be an object.')
    p = deepcopy(raw)
    year, month = p.get('year'), p.get('month')
    if type(year) is not int or type(month) is not int or not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError('year/month must be a valid year (2000..2100) and month.')
    p['days'] = monthrange(year, month)[1]
    p.setdefault('maxExtraOffSpread', 1)
    if type(p['maxExtraOffSpread']) is not int or not 0 <= p['maxExtraOffSpread'] <= p['days']:
        raise ValueError('maxExtraOffSpread must be an integer from 0 to period length.')
    p['start'] = date(year, month, 16)
    p.setdefault('requiredStaff', [4, 4, 4])
    p.setdefault('maxReducedSundays', 3)
    def valid_counts(values):
        return isinstance(values, list) and len(values) == 3 and all(type(v) is int and 0 <= v <= 40 for v in values)
    if not valid_counts(p['requiredStaff']):
        raise ValueError('requiredStaff must contain morning, noon and evening counts (0..40).')
    if type(p['maxReducedSundays']) is not int or not 0 <= p['maxReducedSundays'] <= 5:
        raise ValueError('maxReducedSundays must be an integer from 0 to 5.')
    p.setdefault('dailyRequiredStaff', {})
    if not isinstance(p['dailyRequiredStaff'], dict):
        raise ValueError('dailyRequiredStaff must map period days to three counts.')
    daily = {}
    for key, counts in p['dailyRequiredStaff'].items():
        if (not str(key).isdigit() or not 1 <= int(key) <= p['days']
                or int(key) in daily or not valid_counts(counts)):
            raise ValueError('dailyRequiredStaff contains an invalid day or staffing counts.')
        daily[int(key)] = counts
    p['dailyRequiredStaff'] = daily
    if not isinstance(p.get('staff'), list) or not p['staff']:
        raise ValueError('staff must be a nonempty list.')
    ids = set()
    for st in p['staff']:
        if not isinstance(st, dict):
            raise ValueError('Each staff entry must be an object.')
        sid = st.get('id')
        if not isinstance(sid, str) or not sid or sid in ids:
            raise ValueError('Staff IDs must be nonempty and unique.')
        ids.add(sid)
        if st.get('type') not in ('full', 'fulltime', 'part'):
            raise ValueError(f'{sid}: invalid staff type.')
        st.setdefault('dayShiftType', 'both')
        if st['dayShiftType'] not in ('both', 'early', 'late'):
            raise ValueError(f'{sid}: invalid dayShiftType.')
        st.setdefault('nightShiftType', 'all' if st.get('canNightShift') else 'none')
        if st['nightShiftType'] not in ('none', 'all', 'weekday'):
            raise ValueError(f'{sid}: invalid nightShiftType.')
        for field, default, lo, hi in [('monthlyDaysOff', 9, 0, p['days']), ('maxConsecutive', 0, 0, 6), ('maxDaysPerWeek', 3, 1, 7)]:
            st.setdefault(field, default)
            if type(st[field]) is not int or not lo <= st[field] <= hi:
                raise ValueError(f'{sid}: invalid {field}.')
        # dayShiftFlexible：Aのみ・Bのみの人でも、守ると表が作れないときだけ逆の日勤を許す（中間ルール）。
        for field in ('canOvertime', 'allowConsecutivePlus1', 'dayShiftFlexible'):
            st.setdefault(field, False)
            if type(st[field]) is not bool:
                raise ValueError(f'{sid}: {field} must be boolean.')
        if st['type'] == 'part':
            try:
                times = []
                for field in ('startTime', 'endTime'):
                    value = st[field]
                    if not isinstance(value, str) or len(value) != 5 or value[2] != ':':
                        raise ValueError()
                    hh, mm = map(int, value.split(':'))
                    if not 0 <= hh <= 23 or not 0 <= mm <= 59:
                        raise ValueError()
                    times.append(hh * 60 + mm)
                if times[0] >= times[1]:
                    raise ValueError()
            except (KeyError, ValueError, TypeError):
                raise ValueError(f'{sid}: valid same-day part-time start/end required.') from None
    p.setdefault('nightRestRequiredStaff', [])
    selected = p['nightRestRequiredStaff']
    if (not isinstance(selected, list) or any(not isinstance(sid, str) or sid not in ids for sid in selected)
            or len(selected) != len(set(selected))):
        raise ValueError('nightRestRequiredStaff must contain unique registered staff IDs.')
    # 希望休を夜勤後にするのは基本機能。旧バックアップのオン・オフは使用しない。
    p['nightRestRequiredStaff'] = [st['id'] for st in p['staff']
                                   if st['type'] != 'part' and st['nightShiftType'] != 'none']
    p.setdefault('fairnessExcludedStaff', [])
    excluded = p['fairnessExcludedStaff']
    if (not isinstance(excluded, list) or any(not isinstance(sid, str) or sid not in ids for sid in excluded)
            or len(excluded) != len(set(excluded))):
        raise ValueError('fairnessExcludedStaff must contain unique registered staff IDs.')
    p.setdefault('requests', {})
    p.setdefault('shiftRequests', {})
    p.setdefault('locked', {})
    p.setdefault('history', {})
    for field in ('requests', 'shiftRequests', 'locked', 'history'):
        if not isinstance(p[field], dict) or set(p[field]) - ids:
            raise ValueError(f'{field}: unknown staff ID or invalid mapping.')
    for sid, days in p['requests'].items():
        if not isinstance(days, list) or any(type(d) is not int or not 1 <= d <= p['days'] for d in days):
            raise ValueError(f'{sid}: request days must be period-relative integers.')
    for sid, values in p['shiftRequests'].items():
        if not isinstance(values, dict):
            raise ValueError(f'{sid}: shiftRequests must map period day to requested shift.')
        normalized = {}
        for key, value in values.items():
            if (type(key) not in (str, int) or not str(key).isdigit()
                    or not 1 <= int(key) <= p['days'] or int(key) in normalized
                    or not isinstance(value, str)
                    or value not in ('early', 'late', 'overtime', 'night', 'part')):
                raise ValueError(f'{sid}: invalid requested shift or day.')
            normalized[int(key)] = value
        p['shiftRequests'][sid] = normalized
    for sid, values in p['locked'].items():
        if not isinstance(values, dict):
            raise ValueError(f'{sid}: locked must map period day to shift.')
        for key, value in values.items():
            if not str(key).isdigit() or not 1 <= int(key) <= p['days'] or value not in SHIFTS:
                raise ValueError(f'{sid}: invalid locked shift.')
        p['locked'][sid] = {int(k): v for k, v in values.items()}
    for sid, history in p['history'].items():
        if not isinstance(history, list) or len(history) != 7 or any(v not in SHIFTS for v in history):
            raise ValueError(f'{sid}: history must contain exactly seven preceding days, oldest first.')
    p['boundaryComplete'] = set(p['history']) == ids
    # 履歴がない職員の前期7日は試験上のみ休みと仮定する。実運用合格にはしない。
    for sid in ids:
        p['history'].setdefault(sid, ['off'] * 7)
    return p

