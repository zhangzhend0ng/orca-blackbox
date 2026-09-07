# -*- coding: utf-8 -*-
"""Parse lark-cli record-list markdown dumps into structured JSON + stats."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent


def parse_md_table(text):
    lines = text.splitlines()
    # skip leading note lines, find header row starting with '|'
    rows = []
    header = None
    for ln in lines:
        if not ln.strip().startswith('|'):
            continue
        cells = [c.strip() for c in ln.strip().strip('|').split('|')]
        if header is None:
            header = cells
            continue
        if all(re.fullmatch(r'-{3,}', c) for c in cells):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def clean(v):
    if v is None:
        return ''
    # cells like ["ORCA测试"] -> strip list wrapper
    s = v.strip()
    m = re.fullmatch(r'\[(.*)\]', s)
    if m:
        inner = m.group(1).strip()
        parts = [p.strip().strip('"') for p in inner.split(',') if p.strip()]
        return parts[0] if len(parts) == 1 else parts
    return s


def main():
    records = []
    for p in ('records_p1.json', 'records_p2.json'):
        text = (HERE / p).read_text(encoding='utf-8')
        records.extend(parse_md_table(text))

    fields = ['_record_id', 'ID', '用例标题', '一级分类', '父记录', '测试步骤',
              '路径', '功能模块', '功能名称', '二级分类', '优先级', '用例类型',
              '前置条件', '预期结果', '自动化状态']
    out = []
    for r in records:
        item = {}
        for f in fields:
            item[f] = clean(r.get(f, ''))
        out.append(item)

    (HERE / 'records_all.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')

    # stats
    def stat(key):
        from collections import Counter
        c = Counter()
        for it in out:
            v = it[key]
            if isinstance(v, list):
                v = '/'.join(v)
            c[v or '(空)'] += 1
        return c

    buf = []
    buf.append(f'total records: {len(out)}')
    for key in ('一级分类', '二级分类', '功能模块', '优先级', '自动化状态', '用例类型'):
        buf.append(f'\n== {key} ==')
        for k, n in stat(key).most_common():
            buf.append(f'  {n:4d}  {k}')
    report = '\n'.join(buf)
    (HERE / 'stats.txt').write_text(report, encoding='utf-8')
    print(report.encode('utf-8').decode(sys.stdout.encoding or 'utf-8', 'replace'))


if __name__ == '__main__':
    main()
