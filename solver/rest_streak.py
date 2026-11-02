"""希望休と入力済み実績だけの並びを除き、公休は3連休までにする。"""
POLICY = 'requested-off-max3-1'
LIMIT = 3


def candidate_ends(p, sid):
    if p.get('maxConsecutiveOff') != LIMIT:
        return []
    wishes = set(p['requests'].get(sid, []))
    return [end for end in range(1, p['days'] + 1)
            if (end > LIMIT or sid in p['historyProvided'])
            and any(day > 0 and day not in wishes for day in range(end - LIMIT, end + 1))]


def ranges(p, st, row):
    sid, found = st['id'], []
    def off(day):
        if day <= 0:
            return p['history'][sid][6 + day] == 'off'
        return row.get(str(day), row.get(day)) == 'off'
    for end in candidate_ends(p, sid):
        if not all(off(day) for day in range(end - LIMIT, end + 1)):
            continue
        if found and found[-1]['end'] == end - 1:
            found[-1]['end'] = end
            found[-1]['count'] += 1
        else:
            found.append({'start': end - LIMIT, 'end': end, 'count': 1})
    return found


def count(p, assignments):
    return sum(block['count'] for st in p['staff'] for block in ranges(p, st, assignments[st['id']]))
