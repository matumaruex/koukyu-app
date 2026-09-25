"""ソルバーの制約や変数を使わず、完成した表を再集計して検査する。"""
from datetime import timedelta
from .input_data import normalize, SHIFTS


def validate(raw, assignments):
    p = normalize(raw)
    errors = []

    def fail(code, staff=None, day=None, detail=''):
        errors.append(dict(code=code, staff=staff, day=day, detail=detail))

    ids = {s['id'] for s in p['staff']}
    if not isinstance(assignments, dict) or set(assignments) != ids:
        return [dict(code='structure', detail='Staff rows missing or unexpected.')]
    rows = {}
    for st in p['staff']:
        sid = st['id']
        row = assignments[sid]
        if not isinstance(row, dict) or len(row) != p['days'] or set(map(str, row)) != {str(d) for d in range(1, p['days'] + 1)}:
            fail('structure', sid, detail='Missing or extra period days.')
            continue
        values = [row.get(str(d), row.get(d)) for d in range(1, p['days'] + 1)]
        if any(x not in SHIFTS for x in values):
            fail('structure', sid, detail='Unknown shift.')
            continue
        rows[sid] = values
    if errors:
        return errors
    extras = [rows[st['id']].count('off') - st['monthlyDaysOff'] for st in p['staff']]
    if max(extras) - min(extras) > p['maxExtraOffSpread']:
        fail('fairness', detail=f'Extra-off spread exceeds {p["maxExtraOffSpread"]}.')

    for st in p['staff']:
        sid = st['id']
        values = rows[sid]
        hist = p['history'][sid]
        all_days = hist + values
        night_type = st['nightShiftType']
        limit = st['maxConsecutive'] or (2 if st['type'] != 'part' and night_type != 'none' else 5)
        run = 0
        extensions = 0
        weeks = {}
        for i, shift in enumerate(all_days):
            current = i >= 7
            day = i - 6
            dt = p['start'] + timedelta(days=day - 1)
            run = run + 1 if shift not in ('off', 'nightOff') else 0
            if current:
                if run > limit + (1 if st['allowConsecutivePlus1'] else 0):
                    fail('consecutive', sid, day, f'{run} consecutive days')
                if run == limit + 1:
                    extensions += 1
                if (shift == 'nightOff') != (all_days[i - 1] == 'night'):
                    fail('night_link', sid, day)
                if st['type'] == 'part' and shift not in ('off', 'part'):
                    fail('eligibility', sid, day, 'Part-time staff may only work P.')
                if st['type'] != 'part' and shift == 'part':
                    fail('eligibility', sid, day, 'Full-time staff may not work P.')
                if shift == 'night' and (night_type == 'none' or st['type'] == 'part' or (night_type == 'weekday' and dt.weekday() in (4, 5, 6))):
                    fail('night_eligibility', sid, day)
                if shift == 'overtime' and (not st['canOvertime'] or st['type'] == 'part'):
                    fail('overtime_eligibility', sid, day)
                if shift == 'overtime' and all_days[i - 1] == 'overtime':
                    fail('adjacent_overtime', sid, day)
                if day in p['requests'].get(sid, []) and shift != 'off':
                    fail('request', sid, day)
                expected = p['locked'].get(sid, {}).get(day)
                if expected is not None and shift != expected:
                    fail('locked', sid, day)
            if st['type'] == 'part' and shift not in ('off', 'nightOff'):
                monday = dt - timedelta(days=dt.weekday())
                weeks[monday] = weeks.get(monday, 0) + 1
        if extensions > (1 if st['allowConsecutivePlus1'] else 0):
            fail('consecutive_plus_one', sid, detail=f'{extensions} extensions')
        if values.count('off') < st['monthlyDaysOff']:
            fail('days_off', sid, detail=f"{values.count('off')} < {st['monthlyDaysOff']}")
        if values.count('overtime') > 6:
            fail('overtime_limit', sid)
        first_monday = p['start'] - timedelta(days=p['start'].weekday())
        for monday, count in weeks.items():
            if monday >= first_monday and count > st['maxDaysPerWeek']:
                fail('weekly', sid, detail=f'{monday}: {count} > {st["maxDaysPerWeek"]}')

    reduced = 0
    for d in range(1, p['days'] + 1):
        dt = p['start'] + timedelta(days=d - 1)
        counts = [0, 0, 0]
        night_count = 0
        for st in p['staff']:
            shift = rows[st['id']][d - 1]
            night_count += shift == 'night'
            # 生成側のカバー関数を流用せず、時刻から独立に人数を数える。
            ranges = {'early': (420, 960), 'late': (570, 1110), 'overtime': (420, 1110), 'night': (1020, 1440), 'nightOff': (0, 540)}
            if shift == 'part':
                def minutes(value):
                    h, m = map(int, value.split(':'))
                    return h * 60 + m
                span = (minutes(st['startTime']), minutes(st['endTime']))
            else:
                span = ranges.get(shift, (0, 0))
            for j, t in enumerate((420, 600, 1065)):
                counts[j] += span[0] <= t < span[1]
        if night_count != 1:
            fail('night_coverage', day=d, detail=f'{night_count} night staff')
        sunday = dt.weekday() == 6
        for j, count in enumerate(counts):
            if count < (3 if sunday and j < 2 else 4):
                fail('coverage', day=d, detail=f'{(420, 600, 1065)[j]}: {count}')
        if sunday and (counts[0] < 4 or counts[1] < 4):
            reduced += 1
    if reduced > 3:
        fail('sunday_limit', detail=f'{reduced} reduced Sundays')
    return errors
