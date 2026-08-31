# -*- coding: utf-8 -*-
"""
fetch_vision.py - vision snapshot 解析器

parse_snapshot(text) → dict:
  QX 情绪指标 / ZT 涨停家数 / DT 跌停家数 / KQXY 亏钱效应 / HSLN 主力流入(去亿)
  LBGD 连板高度 / SZ 上涨家数 / XD 下跌家数 / PB 今日封板率 / ZTBX 昨涨停表现 / LBBX 昨连板表现
"""
import re

LABEL_MAP = {
    '情绪指标': 'QX',
    '涨停家数': 'ZT',
    '跌停家数': 'DT',
    '亏钱效应': 'KQXY',
    '主力流入': 'HSLN',
    '连板高度': 'LBGD',
    '上涨家数': 'SZ',
    '下跌家数': 'XD',
    '今日封板率': 'PB',
    '昨涨停表现': 'ZTBX',
    '昨连板表现': 'LBBX',
}


def parse_snapshot(text):
    """解析 vision_snap txt (每行 `button "标签：值"`) → {QX: 78, ...}"""
    out = {}
    for line in text.splitlines():
        m = re.search(r'button "([^：:]+)[：:]([^"]+)"', line.strip())
        if not m:
            continue
        label, val = m.group(1).strip(), m.group(2).strip()
        key = LABEL_MAP.get(label)
        if key:
            try:
                out[key] = float(val) if '%' not in val else float(val.rstrip('%'))
            except ValueError:
                out[key] = val
    return out


def fmt(text, key, ndigits=1):
    """按原始快照格式取数: 百分号项还原 %"""
    if key not in text:
        return None
    return text[key]
