"""7・14・15日間への夜勤の集中を、必須条件を変えずに減らす。"""
POLICY = 'rolling-night-distribution-1'
WEIGHT = 100


def eligible(p):
    return [st for st in p['staff'] if p.get('nightDistribution')
            and st['type'] != 'part' and st['nightShiftType'] != 'none']


def windows(n):
    return [length for length in (7, 14, 15) if length <= n]


def score_bound(p):
    n = p['days']
    # 毎日の夜勤は最大1人なので、各区間で全職員の超過合計は区間日数以下。
    return sum((n - length + 1) * length for length in windows(n)) if eligible(p) else 0


def bound(p):
    return score_bound(p) * WEIGHT


def build(model, p, x, night_totals):
    n, terms = p['days'], []
    for st in eligible(p):
        sid, prefix = st['id'], [0]
        for day in range(1, n + 1):
            cumulative = model.new_int_var(0, day, f'{sid}_night_prefix_{day}')
            model.add(cumulative == prefix[-1] + x[sid, day - 1, 'night'])
            prefix.append(cumulative)
        for length in windows(n):
            ceiling = model.new_int_var(0, length, f'{sid}_night_window_cap_{length}')
            model.add_division_equality(ceiling, length * night_totals[sid] + n - 1, n)
            for start in range(n - length + 1):
                excess = model.new_int_var(0, length, f'{sid}_night_cluster_{length}_{start}')
                model.add_max_equality(excess, [prefix[start + length] - prefix[start] - ceiling, 0])
                terms.append(excess)
    if not terms:
        return 0
    total = model.new_int_var(0, score_bound(p), 'night_distribution_penalty')
    model.add(total == sum(terms))
    return WEIGHT * total


def report(p, assignments):
    n, rows = p['days'], {}
    for st in eligible(p):
        sid, values = st['id'], assignments[st['id']]
        nights = [d for d in range(1, n + 1) if values[str(d)] == 'night']
        count, penalty, by_window = len(nights), 0, {}
        prefix = [0]
        for day in range(1, n + 1):
            prefix.append(prefix[-1] + (values[str(day)] == 'night'))
        for length in windows(n):
            cap = (length * count + n - 1) // n
            counts = [prefix[start + length] - prefix[start] for start in range(n - length + 1)]
            excess = sum(max(0, value - cap) for value in counts)
            penalty += excess
            by_window[str(length)] = {'targetMaximum': cap, 'maximum': max(counts), 'penalty': excess}
        rows[sid] = {'nights': nights, 'count': count, 'penalty': penalty, 'windows': by_window}
    return {'policy': POLICY, 'penalty': sum(row['penalty'] for row in rows.values()), 'byStaff': rows}
