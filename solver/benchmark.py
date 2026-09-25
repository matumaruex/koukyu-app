"""実データ由来・厳しい人工条件を同じ手順で計測し、結果を保存する。"""
import json
from copy import deepcopy
from pathlib import Path
from .engine import solve
from .validator import validate

ROOT = Path(__file__).resolve().parents[1]


def cases():
    base = json.loads((ROOT / 'user_data.json').read_text(encoding='utf-8-sig'))
    base.update(year=2026, month=2)
    # 報告書には実名を出さない。
    for i, st in enumerate(base['staff']):
        st['id'] = f'staff_{i + 1:02}'
        st['name'] = f'職員{i + 1:02}'
    for year, month in [(2026, 2), (2026, 3), (2026, 4), (2026, 12), (2028, 2)]:
        p = deepcopy(base); p.update(year=year, month=month)
        yield f'通常条件 {year}/{month:02}', p
    p = deepcopy(base); p['requests'] = {'staff_01': [1, 2, 3], 'staff_03': [8, 9], 'staff_08': [15, 16]}
    yield '希望休を複数人に追加', p
    p = deepcopy(base); p['staff'] = p['staff'][1:]
    yield 'フルタイム1人減', p
    p = deepcopy(base)
    for st in p['staff']:
        st['canOvertime'] = False
    yield '全員A残なし', p
    p = deepcopy(base)
    for st in p['staff']:
        st['nightShiftType'] = 'none'
    yield '夜勤可能者ゼロ', p
    p = deepcopy(base); p['requests'] = {s['id']: [5] for s in p['staff']}
    yield '全員が同じ日を希望休', p
    p = deepcopy(base); p['staff'][7]['maxDaysPerWeek'] = 3
    yield '朝パートを週3日までに制限', p
    p = deepcopy(base)
    for i in range(2):
        st = deepcopy(base['staff'][0]); st.update(id=f'extra_{i}', name=f'追加職員{i + 1}')
        p['staff'].append(st)
    p['locked'] = {'staff_01': {str(d): 'off' for d in range(1, 12)}}
    yield '余剰休の公平分配（2人増員・1人の公休を最低11日に固定）', p


def main():
    target = ROOT / 'solver' / 'results'
    target.mkdir(exist_ok=True)
    report = []
    previous = None
    for i, (title, p) in enumerate(cases()):
        r = solve(p, seconds=12)
        if 'assignments' in r:
            assert not validate(p, r['assignments'])
        item = {'case': title, 'input': p, 'result': r}
        (target / f'case-{i + 1:02}.json').write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = {'case': title, **{k: v for k, v in r.items() if k not in ('assignments', 'carryForward', 'conflictGroups')}}
        summary['conflictGroupCount'] = len(r.get('conflictGroups', []))
        report.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if i == 0 and 'assignments' in r:
            previous = r
    if previous:
        p = deepcopy(next(cases())[1]); p['month'] = 3
        p['history'] = {sid: v['history'] for sid, v in previous['carryForward'].items()}
        r = solve(p, seconds=12)
        if 'assignments' in r:
            assert not validate(p, r['assignments'])
        (target / 'case-13.json').write_text(json.dumps({'case': '前期の生成結果を翌期へ引継ぎ', 'input': p, 'result': r}, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = {'case': '前期の生成結果を翌期へ引継ぎ', **{k: v for k, v in r.items() if k not in ('assignments', 'carryForward', 'conflictGroups')}}
        report.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (target / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
