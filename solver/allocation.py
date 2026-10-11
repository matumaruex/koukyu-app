"""月全体の残業・配置を評価する。完成表の独立検査とは別の計算。"""
from .input_data import overtime_profile
from .overtime_preference import offsets, score_bounds, ideal_balance as ideal_balance_fn, active

POLICY = 'quality-first-10'
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


# 比率で比べる人がいる月の目盛り。普通の人の1回＝100。出勤できる日数がとても少ない人の係数は6倍で頭打ち。
OVERTIME_SCALE = 100


def overtime_scales(p):
    """残業回数を比べるときの換算係数（A残できるフルタイムで、出勤できる日がある人）。
    出勤できる日数が少ない人がいなければ全員1（3.25と同じ「回数の差」）。いれば普通の人100、
    少ない人は 100×普通の出勤日数÷出勤できる日数（四捨五入、600まで）。"""
    eligible = [(st, overtime_profile(p, st)) for st in p['staff']
                if st.get('type') != 'part' and st.get('canOvertime')]
    eligible = [(st, v) for st, v in eligible if v['available'] > 0]
    if not any(v['proportional'] for _, v in eligible):
        return {st['id']: 1 for st, _ in eligible}
    return {st['id']: (min(6 * OVERTIME_SCALE, (2 * OVERTIME_SCALE * v['normal'] + v['available']) // (2 * v['available']))
                       if v['proportional'] else OVERTIME_SCALE) for st, v in eligible}


def overtime_balance_bound(p):
    """比率と歓迎を換算した値の差の上限。歓迎の分だけ下限は負になる。"""
    scales = overtime_scales(p)
    low, high = score_bounds(p, scales)
    return high - low


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
    # 残業回数差は、出勤できる日数で換算した回数の差。普通の月は3.25と同じく上限6。
    # 比率で比べる人がいる月は最大でおよそ1200（上限回数×係数）になるが、40人・31日でも約1.4e17で64bit整数に収まる。
    balance_bound = overtime_balance_bound(p) if 'days' in p and all('id' in st for st in p['staff']) else 6
    # 残業合計 → 残業回数差 → 人数超過 → 追加公休 → 細部。
    bounds = (6 * k, balance_bound, 3 * k * n, n, minor_bound)
    result, lower = [], 0
    for bound in reversed(bounds):
        result.append(lower + 1)
        lower += bound * (lower + 1)
    w = tuple(reversed(result))
    # 呼び出し側の項の並び（合計・超過・差・公休・細部）は維持する。
    return (w[0], w[2], w[1], w[3], w[4]), lower + 1


def metrics(p, assignments):
    n = p['days']
    ot, extras, nights = {}, [], []
    plain, scaled, proportional = [], [], False
    scales = overtime_scales(p)
    extra = offsets(p, scales)
    preferred = active(p)
    for st in p['staff']:
        row = assignments[st['id']]
        values = [row[str(d)] for d in range(1, n + 1)]
        if st['type'] != 'part' and st['canOvertime']:
            ot[st['id']] = values.count('overtime')
            profile = overtime_profile(p, st)
            if st['id'] in scales:
                scaled.append(ot[st['id']] * scales[st['id']] - extra[st['id']])
            if profile['proportional']:
                proportional = True
            else:
                plain.append(ot[st['id']])
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
    # 画面に出す「差」は、出勤できる日数が普通の人どうしの回数差。
    ot_range = max(plain) - min(plain) if plain else 0
    # 計算で比べる値：出勤できる日数で換算し、歓迎の上乗せを引いた値の差。
    ot_balance = max(scaled) - min(scaled) if scaled else 0
    # 全員が普通の人なら、合計を人数で割り切れないときの差1回が算術上の最少。比率を含む場合は決めない。
    ideal_balance = int(sum(scaled) % len(scaled) != 0) if scaled and not proportional else 0
    if preferred:
        # 上限・0回・比率を含めた整数配分の下限。日付制約まで含む最少は探索で確認する。
        ideal_balance = ideal_balance_fn(p, scales, sum(ot[sid] for sid in scales))
    ab = ab_ratio_report(p, assignments)
    night_spread = max(nights) - min(nights) if nights else 0
    balance = ab['deviationTotal'] + (100 * len(p['staff']) + 1) * night_spread
    minor = spread * minor_unit(p)
    minor += sum(v * v for v in ot.values()) + balance
    return {'overtimeTotal': sum(ot.values()), 'overtimeByStaff': ot,
            'overtimeSpread': ot_range, 'overtimeBalance': ot_balance,
            'overtimeIdealBalance': ideal_balance, 'overtimeProportional': proportional,
            **({'overtimePreferred': True} if preferred else {}),
            'surplusTotal': surplus,
            'commonExtraDaysOff': common, 'extraOffSpread': spread,
            'nightSpread': night_spread, 'abRatioBalance': ab, 'minor': minor}


def quality_value(p, assignments):
    m = metrics(p, assignments)
    terms = (m['overtimeTotal'], m['surplusTotal'], m['overtimeBalance'],
             p['days'] - m['commonExtraDaysOff'], m['minor'])
    return sum(v * w for v, w in zip(terms, weights(p)[0]))
