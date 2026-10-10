"""A残は1回の出勤サイクルに1回まで（3.40）。
出勤サイクル＝公休・明けで区切った出勤のひと続き（夜勤を含む）。人数不足を減らすためだけに2回目以降を許す（できるだけ守る目標）。
希望勤務・固定のA残も、計算が入れたA残と同じく数える（オーナーの指定）。希望・固定どうしが同じサイクルなら、
計算は間に公休を入れてサイクルを分けようとし、分けられなければ2回目として表示する。
前期の実績が入力されていれば、境目のサイクルもつなげる（前期未入力の仮定の休みでは区切りもつなげもしない）。
計算側（engine の状態変数）と同じ数え方：日ごとに、A残の日はそのサイクルに既にA残があれば1。"""


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
    """1サイクルに2回目以降となったA残の数（excess）と、そのサイクル。指定がない入力では None。
    wishOnly：そのサイクルの今期のA残がすべて希望・固定（計算が入れたA残がない）。"""
    if not p.get('overtimeCycleLimit'):
        return None
    items = []
    for st in p['staff']:
        if not eligible(st):
            continue
        sid = st['id']
        row = assignments[sid]
        seen = carry_in(p, sid)
        start, count, extra, computed = None, 0, 0, 0
        for day in range(1, p['days'] + 2):
            shift = row.get(str(day), row.get(day)) if day <= p['days'] else 'off'
            if shift in ('off', 'nightOff'):
                if extra:
                    items.append({'staff': sid, 'start': start, 'end': day - 1, 'overtime': count,
                                  'count': extra, 'wishOnly': not computed})
                seen, start, count, extra, computed = 0, None, 0, 0, 0
                continue
            if start is None:
                start = day
            if shift != 'overtime':
                continue
            extra += seen
            seen, count = 1, count + 1
            computed += not fixed_overtime(p, sid, day)
    return {'excess': sum(item['count'] for item in items), 'items': items}
