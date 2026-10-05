"""希望休の前の夜勤を優先する。希望休自体と実際の夜勤後の休みは別の必須条件。"""


def targets(p):
    for sid in p['nightRestRequiredStaff']:  # 既存バックアップの項目名を維持。
        requested = set(p['requests'].get(sid, []))
        for day in sorted(requested):
            if day - 1 not in requested:
                yield sid, day


def report(p, assignments):
    unmet, total = [], 0
    for sid, day in targets(p):
        total += 1
        def shift(d):
            return p['history'][sid][d + 6] if d <= 0 else assignments[sid].get(str(d), assignments[sid].get(d))
        if shift(day - 2) != 'night' or shift(day - 1) != 'nightOff':
            unmet.append({'staff': sid, 'day': day, 'nightDay': day - 2,
                          'actualNightDay': shift(day - 2), 'actualRecoveryDay': shift(day - 1)})
    return {'requestedCount': total, 'metCount': total - len(unmet), 'unmet': unmet}
