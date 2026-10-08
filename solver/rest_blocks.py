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
