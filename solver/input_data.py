"""入力形式を検査・正規化する。シフトを組む処理は含めない。"""
from calendar import monthrange
from copy import deepcopy
from datetime import date, timedelta

SHIFTS = ('off', 'early', 'late', 'overtime', 'night', 'nightOff', 'part')
OVERTIME_MONTHLY_LIMIT = 6


def overtime_profile(p, st):
    """出勤できる日数から、A残の上限を決める。
    出勤できる日数＝期間日数−max(公休の最低日数, 希望休の日数)。作る前に決まる値なので計算が重くならない。
    希望休が最低日数以内の人は普通の人と同じ（上限6回）。長期休暇などで希望休が多い人は、
    上限6回を「出勤できる日数÷普通の出勤日数」の比率で縮める（切り上げ）。"""
    n = p['days']
    normal = n - st['monthlyDaysOff']
    available = n - max(st['monthlyDaysOff'], len(set(p['requests'].get(st['id'], []))))
    if normal <= 0 or available >= normal:
        return {'available': max(available, 0), 'normal': max(normal, 0), 'proportional': False,
                'cap': OVERTIME_MONTHLY_LIMIT}
    if available <= 0:
        return {'available': 0, 'normal': normal, 'proportional': True, 'cap': 0}
    cap = min(OVERTIME_MONTHLY_LIMIT, (OVERTIME_MONTHLY_LIMIT * available + normal - 1) // normal)
    return {'available': available, 'normal': normal, 'proportional': True, 'cap': cap}


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
    # A残は1回の出勤サイクルに1回まで（3.40、通常版の画面が送る。人数不足を減らすためだけに2回目を許す）。
    p.setdefault('overtimeCycleLimit', False)
    if type(p['overtimeCycleLimit']) is not bool:
        raise ValueError('overtimeCycleLimit must be boolean.')
    # 連休の設定をした人どうしの連休の回数の差を1回以内に（3.46、通常版の画面が連休の設定をした人がいるときだけ送る）。
    p.setdefault('restCountBalance', False)
    if type(p['restCountBalance']) is not bool:
        raise ValueError('restCountBalance must be boolean.')
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
        for field, default, lo, hi in [('monthlyDaysOff', 9, 0, p['days']), ('minConsecutiveRest', 0, 0, 2), ('overtimePreference', 0, 0, 2), ('maxConsecutive', 0, 0, 6), ('maxDaysPerWeek', 3, 1, 7)]:
            st.setdefault(field, default)
            if type(st[field]) is not int or not lo <= st[field] <= hi:
                raise ValueError(f'{sid}: invalid {field}.')
        # dayShiftFlexible：Aのみ・Bのみの人でも、守ると表が作れないときだけ逆の日勤を許す（中間ルール）。
        # noConsecutiveRest：この人には連休（2日以上続く公休）を作らない。連休の必須回数とは同時に指定できない。
        # nightRemainderPriority：夜勤が割り切れないとき、多いほうの回数を優先して受け持つ（夜勤できるフルタイムだけ有効）。
        for field in ('canOvertime', 'allowConsecutivePlus1', 'dayShiftFlexible', 'noConsecutiveRest', 'nightRemainderPriority'):
            st.setdefault(field, False)
            if type(st[field]) is not bool:
                raise ValueError(f'{sid}: {field} must be boolean.')
        if st['noConsecutiveRest'] and st['minConsecutiveRest']:
            raise ValueError(f'{sid}: noConsecutiveRest cannot be combined with minConsecutiveRest.')
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
    # 実際に前期の勤務が入力された職員。仮定の休み（下の補完）とは区別する。
    p['historyProvided'] = set(p['history'])
    # 履歴がない職員の前期7日は試験上のみ休みと仮定する。実運用合格にはしない。
    for sid in ids:
        p['history'].setdefault(sid, ['off'] * 7)
    return p

