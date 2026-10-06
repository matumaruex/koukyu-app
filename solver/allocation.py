"""月全体の残業・配置を評価する。完成表の独立検査とは別の計算。"""

POLICY = 'quality-first-1'
CHECKPOINTS = (420, 600, 1065)


def covers(st, shift, checkpoint):
    if shift == 'part':
        if st['type'] != 'part':
            return False
        start = int(st['startTime'][:2]) * 60 + int(st['startTime'][3:])
        end = int(st['endTime'][:2]) * 60 + int(st['endTime'][3:])
        return start <= checkpoint < end
    return shift in {420: ('early', 'overtime', 'nightOff'),
                     600: ('early', 'late', 'overtime'),
                     1065: ('late', 'overtime', 'night')}[checkpoint]


def minor_unit(p):
    n, k = p['days'], len(p['staff'])
    # 夜勤の差1回を、A/B比率だけの改善で逆転しない。
    return 36 * k + n * (100 * k + 1) + 100 * k + 1


def ab_ratio_report(p, assignments):
    rows = {}
    for st in p['staff']:
        if st['type'] == 'part' or st['dayShiftType'] != 'both':
            continue
        values = [assignments[st['id']][str(d)] for d in range(1, p['days'] + 1)]
        a, b = values.count('early'), values.count('late')
        days = a + b
        rows[st['id']] = {'early': a, 'late': b, 'days': days,
                         'earlyPercent': (200 * a + days) // (2 * days) if days else None}
    total_a = sum(row['early'] for row in rows.values())
    total_days = sum(row['days'] for row in rows.values())
    target = (200 * total_a + total_days) // (2 * total_days) if total_days else None
    deviation = sum(abs(row['earlyPercent'] - target) for row in rows.values() if row['days'])
    return {'targetAPercent': target, 'deviationTotal': deviation, 'byStaff': rows,
            'comparedStaff': [sid for sid, row in rows.items() if row['days']]}


def weights(p):
    n, k = p['days'], len(p['staff'])
    # 全項が非負。1つ上の項1単位を下位の改善で逆転できない係数。
    # 40人・31日・不足3720人分でもCP-SATの64bit整数範囲に収まる。
    minor_bound = (n + 1) * (minor_unit(p) - 1) + n
    bounds = (6 * k, 3 * k * n, 6, n, minor_bound)
    result, lower = [], 0
    for bound in reversed(bounds):
        result.append(lower + 1)
        lower += bound * (lower + 1)
    return tuple(reversed(result)), lower + 1


def metrics(p, assignments):
    n = p['days']
    ot, extras, nights = {}, [], []
    for st in p['staff']:
        row = assignments[st['id']]
        values = [row[str(d)] for d in range(1, n + 1)]
        if st['type'] != 'part' and st['canOvertime']:
            ot[st['id']] = values.count('overtime')
        if st['id'] not in p['fairnessExcludedStaff']:
            extras.append(values.count('off') - st['monthlyDaysOff'])
        if st['type'] != 'part':
            if st['nightShiftType'] != 'none':
                nights.append(values.count('night'))
    surplus = 0
    for d in range(1, n + 1):
        needs = p['dailyRequiredStaff'].get(d, p['requiredStaff'])
        for j, t in enumerate(CHECKPOINTS):
            count = sum(covers(st, assignments[st['id']][str(d)], t) for st in p['staff'])
            # 日曜の許可された削減は不足側で検査する。削減フラグ自体を
            # 余剰として罰せず、通常の必要人数を超える人数だけを数える。
            surplus += max(0, count - needs[j])
    spread = max(extras) - min(extras) if extras else 0
    common = min(extras) if extras else 0
    ot_range = max(ot.values()) - min(ot.values()) if ot else 0
    ab = ab_ratio_report(p, assignments)
    night_spread = max(nights) - min(nights) if nights else 0
    balance = ab['deviationTotal'] + (100 * len(p['staff']) + 1) * night_spread
    minor = spread * minor_unit(p)
    minor += sum(v * v for v in ot.values()) + balance
    return {'overtimeTotal': sum(ot.values()), 'overtimeByStaff': ot,
            'overtimeSpread': ot_range, 'surplusTotal': surplus,
            'commonExtraDaysOff': common, 'extraOffSpread': spread,
            'nightSpread': night_spread, 'abRatioBalance': ab, 'minor': minor}


def quality_value(p, assignments):
    m = metrics(p, assignments)
    terms = (m['overtimeTotal'], m['surplusTotal'], m['overtimeSpread'],
             p['days'] - m['commonExtraDaysOff'], m['minor'])
    return sum(v * w for v, w in zip(terms, weights(p)[0]))

