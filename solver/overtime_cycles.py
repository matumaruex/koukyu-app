"""A残は1回の出勤サイクルに1回まで（3.40）。
出勤サイクル＝公休・明けで区切った出勤のひと続き（夜勤を含む）。人数不足を減らすためだけに2回目以降を許す（できるだけ守る目標）。
希望勤務・固定のA残どうしは希望どおりで数えない。計算が入れたA残と同じサイクルになった分を数える。
前期の実績が入力されていれば、境目のサイクルもつなげる（前期未入力の仮定の休みでは区切りもつなげもしない）。
計算側（engine の状態変数）と同じ順で数える：日ごとに、計算が入れたA残はそのサイクルに既にA残があれば1、
希望・固定のA残はそのサイクルに計算が入れたA残が既にあれば1。"""


def eligible(st):
    return st['canOvertime'] and st['type'] != 'part'


def fixed_overtime(p, sid, day):
    """希望勤務か固定でA残にした日か（day は期間の何日目、1始まり）。"""
    return (p['shiftRequests'].get(sid, {}).get(day) == 'overtime'
            or p['locked'].get(sid, {}).get(day) == 'overtime')


def carry_in(p, sid):
    """前期の最後の公休・明けより後にA残があれば、今期1日目からのサイクルに持ち越す。"""
    carry = 0
    if sid in p['historyProvided']:
        for shift in p['history'][sid]:
            carry = 1 if shift == 'overtime' else 0 if shift in ('off', 'nightOff') else carry
    return carry


def report(p, assignments):
    """1サイクルに2回目以降となったA残の数（excess）と、そのサイクル。指定がない入力では None。"""
    if not p.get('overtimeCycleLimit'):
        return None
    items = []
    for st in p['staff']:
        if not eligible(st):
            continue
        sid = st['id']
        row = assignments[sid]
        seen, free = carry_in(p, sid), 0
        start, count, extra = None, 0, 0
        for day in range(1, p['days'] + 2):
            shift = row.get(str(day), row.get(day)) if day <= p['days'] else 'off'
            if shift in ('off', 'nightOff'):
                if extra:
                    items.append({'staff': sid, 'start': start, 'end': day - 1, 'overtime': count, 'count': extra})
                seen, free, start, count, extra = 0, 0, None, 0, 0
                continue
            if start is None:
                start = day
            if shift != 'overtime':
                continue
            fixed = fixed_overtime(p, sid, day)
            extra += free if fixed else seen
            seen, count = 1, count + 1
            if not fixed:
                free = 1
    return {'excess': sum(item['count'] for item in items), 'items': items}
