"""期間内の公休だけを数える。明け・前期・次期の休みは連休の回数に含めない。"""


def ranges(row, days):
    blocks, start = [], None
    for day in range(1, days + 2):
        shift = row.get(str(day), row.get(day)) if day <= days else None
        if shift == 'off':
            if start is None:
                start = day
        elif start is not None:
            if day - start >= 2:
                blocks.append({'start': start, 'end': day - 1})
            start = None
    return blocks


def report(p, assignments):
    result = {}
    for st in p['staff']:
        if st['minConsecutiveRest']:
            blocks = ranges(assignments[st['id']], p['days'])
            result[st['id']] = {'required': st['minConsecutiveRest'],
                                'actual': len(blocks), 'ranges': blocks}
    return result


def user_fixed_off(p, sid, day):
    """計算が決めた休みではない日：前期の実績、希望休、固定した公休。連休なしの判定で、両日ともこれなら例外にしない。"""
    if day <= 0:
        return True
    return day in p['requests'].get(sid, []) or p['locked'].get(sid, {}).get(day) == 'off'


def forbidden_pairs(p, st, row):
    """連休なしの人について、連続した公休の組（前日・当日）のうち計算が作ったものを返す。
    明けは休みに数えない。前期の最終日は、実際に入力された前期の勤務が公休のときだけつなげる。"""
    sid, pairs = st['id'], []
    if not st.get('noConsecutiveRest'):
        return pairs
    def off(day):
        if day <= 0:
            return sid in p['historyProvided'] and p['history'][sid][6 + day] == 'off'
        return row.get(str(day), row.get(day)) == 'off'
    for day in range(1, p['days'] + 1):
        if off(day) and off(day - 1) and not (user_fixed_off(p, sid, day - 1) and user_fixed_off(p, sid, day)):
            pairs.append(day)
    return pairs


def forbidden_ranges(p, st, row):
    """連休なしの例外を、ひと続きの連休ごとにまとめる（start は前期の最終日なら0）。count は例外の数（組の数）。"""
    result = []
    for day in forbidden_pairs(p, st, row):
        if result and result[-1]['end'] == day - 1:
            result[-1]['end'] = day
            result[-1]['count'] += 1
        else:
            result.append({'start': day - 1, 'end': day, 'count': 1})
    return result


def counted_ranges(p, sid, row):
    """連休の回数の比較（3.46）に数える連休：希望休・固定の公休だけでできた連休は数えない。
    計算が決めた公休を1日でも含む連休だけを数える。今期内の連休だけ（前期・翌期とはつなげない）。"""
    return [b for b in ranges(row, p['days'])
            if any(not user_fixed_off(p, sid, d) for d in range(b['start'], b['end'] + 1))]


def balance_staff(p):
    """連休の回数を比べる人：連休の設定（月1回以上・2回以上）をした人。公休の比較から外した人は除く。"""
    if not p.get('restCountBalance'):
        return []
    staff = [st for st in p['staff'] if st['minConsecutiveRest'] and st['id'] not in p['fairnessExcludedStaff']]
    return staff if len(staff) >= 2 else []


def balance_report(p, assignments):
    """連休の回数の差（3.46）：比べる人の回数と、差が1回を超えた分（excess）。比べる人が2人未満なら None。"""
    staff = balance_staff(p)
    if not staff:
        return None
    counts = {st['id']: len(counted_ranges(p, st['id'], assignments[st['id']])) for st in staff}
    high, low = max(counts.values()), min(counts.values())
    return {'counts': counts, 'high': high, 'low': low, 'excess': max(0, high - low - 1)}
