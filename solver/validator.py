"""ソルバーの制約や変数を使わず、完成した表を再集計して検査する。"""
from datetime import timedelta
from .input_data import normalize, SHIFTS, overtime_profile
from .rest_blocks import ranges as rest_ranges, forbidden_ranges, balance_report as rest_balance_report
from .night_remainder import report as night_remainder_report

SHORTFALL_CODES = ('coverage', 'sunday_limit')


def is_rule_exception(p, error):
    """中間ルール（守ると表が作れないときだけ破れる）の違反か。p は正規化済みの入力。"""
    if error['code'] in ('consecutive', 'consecutive_plus_one', 'no_consecutive_rest', 'night_remainder', 'rest_balance'):
        return True
    if error['code'] == 'day_shift_eligibility':
        staff = next((st for st in p['staff'] if st['id'] == error['staff']), None)
        return bool(staff and staff['dayShiftFlexible'])
    return False


def exception_count(p, errors):
    """計算側と同じ数え方：上限を超えた日数＋＋1の超過回数＋逆の日勤の日数。
    連休なしの例外は、最初に最少回数を証明して固定する別扱いなので、ここには数えない（rest_exception_count）。"""
    return sum(e.get('count', 1) for e in errors
               if is_rule_exception(p, e) and e['code'] not in ('no_consecutive_rest', 'night_remainder', 'rest_balance'))


def rest_exception_count(errors):
    """連休なしの例外の数（連続した公休の組の数）。"""
    return sum(e.get('count', 1) for e in errors if e['code'] == 'no_consecutive_rest')


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
    extras = [rows[st['id']].count('off') - st['monthlyDaysOff'] for st in p['staff']
              if st['id'] not in p['fairnessExcludedStaff']]
    if len(extras) >= 2 and max(extras) - min(extras) > p['maxExtraOffSpread']:
        fail('fairness', detail=f'Extra-off spread exceeds {p["maxExtraOffSpread"]}.')

    for st in p['staff']:
        sid = st['id']
        values = rows[sid]
        hist = p['history'][sid]
        all_days = hist + values
        night_type = st['nightShiftType']
        limit = st['maxConsecutive'] or 3
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
                    errors[-1].update(actual=run, limit=limit, plusOne=st['allowConsecutivePlus1'])
                if run == limit + 1:
                    extensions += 1
                if (shift == 'nightOff') != (all_days[i - 1] == 'night'):
                    fail('night_link', sid, day)
                if all_days[i - 1] == 'nightOff' and shift != 'off':
                    fail('night_rest', sid, day, 'A public holiday is required after night-shift recovery.')
                if st['type'] == 'part' and shift not in ('off', 'part'):
                    fail('eligibility', sid, day, 'Part-time staff may only work P.')
                if st['type'] != 'part' and shift == 'part':
                    fail('eligibility', sid, day, 'Full-time staff may not work P.')
                if st['type'] != 'part' and ((st['dayShiftType'] == 'early' and shift == 'late')
                                             or (st['dayShiftType'] == 'late' and shift == 'early')):
                    fail('day_shift_eligibility', sid, day)
                    errors[-1].update(allowed=st['dayShiftType'], actual=shift)
                if shift == 'night' and (night_type == 'none' or st['type'] == 'part' or (night_type == 'weekday' and dt.weekday() in (4, 5, 6))):
                    fail('night_eligibility', sid, day)
                if shift == 'overtime' and (not st['canOvertime'] or st['type'] == 'part'):
                    fail('overtime_eligibility', sid, day)
                if shift == 'overtime' and all_days[i - 1] == 'overtime':
                    fail('adjacent_overtime', sid, day)
                if day in p['requests'].get(sid, []) and shift != 'off':
                    fail('request', sid, day)
                requested = p['shiftRequests'].get(sid, {}).get(day)
                if requested is not None and shift != requested:
                    fail('shift_request', sid, day)
                    errors[-1].update(requested=requested, actual=shift)
                expected = p['locked'].get(sid, {}).get(day)
                if expected is not None and shift != expected:
                    fail('locked', sid, day)
            if st['type'] == 'part' and shift not in ('off', 'nightOff'):
                monday = dt - timedelta(days=dt.weekday())
                weeks[monday] = weeks.get(monday, 0) + 1
        # ＋1を許可していない人の上限超えは consecutive として日ごとに報告済み。
        if st['allowConsecutivePlus1'] and extensions > 1:
            fail('consecutive_plus_one', sid, detail=f'{extensions} extensions')
            errors[-1].update(actual=extensions, allowed=1, count=extensions - 1, limit=limit)
        if values.count('off') < st['monthlyDaysOff']:
            fail('days_off', sid, detail=f"{values.count('off')} < {st['monthlyDaysOff']}")
        if st['minConsecutiveRest']:
            blocks = rest_ranges(assignments[sid], p['days'])
            if len(blocks) < st['minConsecutiveRest']:
                fail('rest_blocks', sid, detail='連休の必須回数に届いていません。')
                errors[-1].update(actual=len(blocks), required=st['minConsecutiveRest'], ranges=blocks)
        for block in forbidden_ranges(p, st, assignments[sid]):
            fail('no_consecutive_rest', sid, block['end'], '連休なしの職員に連休があります。')
            errors[-1].update(start=block['start'], end=block['end'], count=block['count'])
        cap = overtime_profile(p, st)['cap']
        if values.count('overtime') > cap:
            fail('overtime_limit', sid, detail=f"{values.count('overtime')} > {cap}")
            errors[-1].update(actual=values.count('overtime'), limit=cap)
        first_monday = p['start'] - timedelta(days=p['start'].weekday())
        for monday, count in weeks.items():
            if monday >= first_monday and count > st['maxDaysPerWeek']:
                fail('weekly', sid, detail=f'{monday}: {count} > {st["maxDaysPerWeek"]}')

    # 夜勤の端数優先：目安を超えた夜勤が許容量を超えたときだけ、目安を超えた人を例外として報告する。
    remainder = night_remainder_report(p, {sid: dict(zip(map(str, range(1, p['days'] + 1)), rows[sid])) for sid in rows})
    if remainder and remainder['exceptions']:
        for sid, over in remainder['over'].items():
            fail('night_remainder', sid, detail='夜勤の端数を優先する人以外に、目安を超える夜勤があります。')
            errors[-1].update(actual=remainder['counts'][sid], fair=remainder['fair'][sid], count=over,
                              priority=sid in remainder['priority'], exceptions=remainder['exceptions'])

    # 連休の回数の差（3.46）：連休の設定をした人どうしで1回を超えた分を、1件の例外として報告する。
    balance = rest_balance_report(p, {sid: dict(zip(map(str, range(1, p['days'] + 1)), rows[sid])) for sid in rows})
    if balance and balance['excess']:
        fail('rest_balance', detail='連休の設定をした人どうしの連休の回数の差が1回を超えています。')
        errors[-1].update(counts=balance['counts'], high=balance['high'], low=balance['low'], count=balance['excess'])

    coverage_days = []
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
            errors[-1].update(actual=night_count, required=1)
        needs = p['dailyRequiredStaff'].get(d, p['requiredStaff'])
        sunday = dt.weekday() == 6 and d not in p['dailyRequiredStaff'] and p['maxReducedSundays'] > 0
        coverage_days.append((d, counts, needs, sunday))
    # ソルバーの緩和変数を信用せず、実人数から有効な日曜の割当を再評価。
    reduced = [row for row in coverage_days if row[3] and any(row[1][i] < row[2][i] for i in (0, 1))]
    benefit = lambda row: sum(row[1][i] < row[2][i] for i in (0, 1))
    allowed = {row[0] for row in sorted(reduced, key=lambda row: (-benefit(row), row[0]))[:p['maxReducedSundays']]}
    for d, counts, needs, sunday in coverage_days:
        for j, count in enumerate(counts):
            need = max(0, needs[j] - 1) if d in allowed and j < 2 else needs[j]
            if count < need:
                fail('coverage', day=d, detail=f'{(420, 600, 1065)[j]}: {count} < {need}')
                errors[-1].update(time=(420, 600, 1065)[j], actual=count, required=need)
    if len(reduced) > p['maxReducedSundays']:
        fail('sunday_limit', detail=f'{len(reduced)} reduced Sundays > {p["maxReducedSundays"]}')
        errors[-1].update(days=[row[0] for row in reduced], actual=len(reduced), required=p['maxReducedSundays'])
    return errors
