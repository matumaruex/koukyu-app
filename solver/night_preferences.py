"""希望休直前の明けと、明け・公休1日を同列に評価する独立集計。"""

RULE = 'night-request-gap-1'


def targets(p):
    for sid in p['nightRestRequiredStaff']:  # 正規化済みの夜勤可能な職員全員。
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
        direct = shift(day - 2) == 'night' and shift(day - 1) == 'nightOff'
        spaced = (shift(day - 3) == 'night' and shift(day - 2) == 'nightOff'
                  and shift(day - 1) == 'off')
        if not (direct or spaced):
            unmet.append({'staff': sid, 'day': day, 'nightDay': day - 2,
                          'nightDays': [day - 2, day - 3],
                          'actualNightDay': shift(day - 2), 'actualRecoveryDay': shift(day - 1)})
    return {'rule': RULE, 'requestedCount': total, 'metCount': total - len(unmet), 'unmet': unmet}

