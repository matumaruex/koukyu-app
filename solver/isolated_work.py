"""公休に挟まれた1日だけの出勤。明け・未知の実績や次期を公休扱いにしない。"""

POLICY = 'off-work-off-1'
WORK_SHIFTS = ('early', 'late', 'overtime', 'part', 'night')


def days(p, st, row):
    if not st.get('avoidIsolatedWork'):
        return []
    sid = st['id']
    def shift(day):
        if day <= 0:
            return p['history'][sid][6 + day] if sid in p['historyProvided'] else None
        return row.get(str(day), row.get(day))
    # 今期の選択で並びが変わる前期最終日も対象。未知の次期にはつなげない。
    return [d for d in range(0, p['days'])
            if shift(d - 1) == 'off' and shift(d) in WORK_SHIFTS and shift(d + 1) == 'off']


def count(p, assignments):
    return sum(len(days(p, st, assignments[st['id']])) for st in p['staff'])
