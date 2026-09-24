#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_report.py - fupan v2.9.18 (2026-09-24 家数口径统一 + xychart 语法修复)

生成 A股市场复盘报告 (Markdown):
  §1 市场概览 (1.1 A股指数 / 1.2 全球对比) ← global.json
  §2 市场情绪 (2.1 面板 / 2.2 统计 / 2.3 连扳梯队 / 2.4 晋级率 / 2.5 综合) ← vision + pools + jinji
  §3 涨幅排行榜 (3.1 TOP15 / 3.2 成交额 TOP10) ← ztpool
  §4 题材全景图 (4.1 热度 / 4.2 15字段详表 / 4.3 mermaid) ← zthis_sectors.json
  §5 板块涨跌幅 (5.1 涨幅 / 5.2 跌幅) ← zthis + dtpool
  §6 主力资金 (6.1 流入 / 6.2 流出) ← zthis + dtpool 反推
  附录 A 跌停 / 附录 B 炸板 + 成交额 xychart ← pools
  📝 复盘总结

铁律 (v2.9.1/2.9.4/2.9.7):
  - 必须传 --vision-snapshot (不传 = qxlive 缓存 = 报告污染, FATAL)
  - §2.1/§2.2 情绪 11 项用 vision 真实值
  - §4.1/§5.1/§6.1 永远用 zthis_sectors.json, 不用 Counter 反推
  - 数据源标注不可省略

用法:
  python gen_report.py --vision-snapshot /path/vision_snap_YYYYMMDD.txt [--date YYYY-MM-DD]
"""
import json
import os
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_vision import parse_snapshot

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\cosmo'), 'Desktop')
OUT_DIR = os.path.join(DESKTOP, '股票账户监管', 'hermes每日复盘数据')
BJT = timezone(timedelta(hours=8))
BJT_TODAY = datetime.now(BJT).strftime('%Y-%m-%d')

WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

# ── 参数 ──
DATE_STR = BJT_TODAY
_vision_snap_path = None
argv = sys.argv[1:]
for i, a in enumerate(argv):
    if a == '--date' and i + 1 < len(argv):
        DATE_STR = argv[i + 1]
    if a == '--vision-snapshot' and i + 1 < len(argv):
        _vision_snap_path = argv[i + 1]

if not _vision_snap_path:
    print('[FATAL] v2.9.7 铁律: 必须传 --vision-snapshot (不传 = qxlive 缓存 = 报告污染)')
    sys.exit(1)
# 相对路径防御: 调用方 cwd 可能是 Desktop, snapshot 在 scripts/ 下
if not os.path.isabs(_vision_snap_path):
    cand = os.path.join(SCRIPT_DIR, _vision_snap_path)
    if os.path.isfile(cand):
        _vision_snap_path = cand
if not os.path.isfile(_vision_snap_path):
    print(f'[FATAL] vision snapshot 不存在: {_vision_snap_path}')
    sys.exit(1)

# ── vision snapshot 解析 (v2.9.1: 必须真实值) ──
_e = parse_snapshot(open(_vision_snap_path, encoding='utf-8').read())
if len(_e) < 11:
    print(f'[WARN] vision snapshot 仅解析 {len(_e)}/11 项, 缺失项用 qxlive fallback')
_qx = _e.get('QX')
_zt = _e.get('ZT')
_dt = _e.get('DT')


def _load_json(name):
    """读 Desktop JSON, 缺失/坏文件返回 None"""
    p = os.path.join(DESKTOP, name)
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return None


# ── 数据加载 ──
_global = _load_json('global.json')
_jinji = _load_json('jinji.json')
_qxlive = _load_json('qxlive.json')
_pools = {}
for f in ['ztpool', 'zbpool', 'dtpool', 'lbpool', 'czpool', 'dmpool', 'fxpool']:
    _pools[f] = _load_json(f'{f}.json')


def _pool_list(tag):
    d = _pools.get(tag) or {}
    lst = d.get('list')
    return lst if isinstance(lst, list) else []


# ── emotion_now 11 项 (vision 优先, qxlive fallback) ──
def _qx(key, fallback=None):
    if key in _e:
        return _e[key]
    q = (_qxlive or {}).get('qxlast') or {}
    arr = q.get(key) or []
    if arr:
        try:
            return float(str(arr[-1]).rstrip('%'))
        except Exception:
            return arr[-1]
    return fallback


EMOTION_NOW = {
    'QX': _qx('QX'), 'ZT': _qx('ZT'), 'DT': _qx('DT'), 'KQXY': _qx('KQXY'),
    'HSLN': _qx('HSLN'), 'LBGD': _qx('LBGD'), 'SZ': _qx('SZ'), 'XD': _qx('XD'),
    'PB': _qx('PB'), 'ZTBX': _qx('ZTBX'), 'LBBX': _qx('LBBX'),
}

# emotion_vision.json 写盘 (11 项)
try:
    with open(os.path.join(DESKTOP, 'emotion_vision.json'), 'w', encoding='utf-8') as f:
        json.dump({'date': DATE_STR, **EMOTION_NOW}, f, ensure_ascii=False)
except Exception:
    pass


def _fmt_pct(v):
    """浮点 → '1.41' / '20' / '10.1' (去尾零, 不带 %)"""
    if v is None:
        return '—'
    s = f'{float(v):.2f}'
    return s.rstrip('0').rstrip('.') if '.' in s else s


def _fmt_amount_wan(v):
    """元 → 亿 (2 位小数)"""
    try:
        return f'{float(v) / 1e8:.2f}亿'
    except Exception:
        return '—'


# ============================================================
m = []

# ── 头部 ──
_week = WEEKDAYS[datetime.strptime(DATE_STR, '%Y-%m-%d').weekday()]
_dt_obj = datetime.strptime(DATE_STR, '%Y-%m-%d')
m.append(f'# A股市场复盘报告 · {_dt_obj.year}年{_dt_obj.month:02d}月{_dt_obj.day:02d}日（{_week}）')
m.append('')
m.append(f'> 📅 数据日期：**{DATE_STR}**')
m.append('')
m.append('> 🌐 数据来源：[短线侠](https://duanxianxia.cn/web/main) · [东财](https://quote.eastmoney.com/)')
m.append('')
m.append('> 🤖 自动化生成 by 花花（v2.9.0 全实时数据版）')
m.append('')

# ── §1 市场概览 ──
m.append('## 一、市场概览')
m.append('')
m.append('### 1.1 A 股主要指数')
m.append('')
m.append('> ⚠️ 短线侠数据源未包含**科创板 000688** 与**北证 50** 指数。')
m.append('')
m.append('')
m.append('| 指数 | 收盘点位 | 涨跌 | 涨跌幅 |')
m.append('|---|---|---|---|')
m.append('')

_global_diff = ((_global or {}).get('data') or {}).get('diff') or []
_A_NAMES = ['上证指数', '深证成指', '创业板指', '沪深300', '上证50', '中证1000', '中证2000']
_a_items = [g for g in _global_diff if g.get('f14') in _A_NAMES]
# 按历史报告顺序
_order = ['中证1000', '沪深300', '中证2000', '上证50', '上证指数', '深证成指', '创业板指']
_a_items.sort(key=lambda g: _order.index(g.get('f14')) if g.get('f14') in _order else 99)
for g in _a_items:
    nm, price, chg, pct = g.get('f14'), g.get('f2'), g.get('f4'), g.get('f3')
    cls = 'up' if (pct or 0) >= 0 else 'down'
    m.append(f'| {nm} | {price:.2f} | {chg:+.2f} | {pct:+.2f}% |')
if not _a_items:
    m.append('| 指数 | — | — | — |')
m.append('')

m.append('')
m.append('### 1.2 全球市场指数对比')
m.append('')
m.append('')
m.append('| 地区 | 指数 | 收盘 | 涨跌 | 涨跌幅 |')
m.append('|---|---|---|---|---|')
m.append('')

_REGION_MAP = [
    ('美股', ['纳指期货', '小型纳指当月连续', '道指期货', '小型道指当月连续', '道琼斯', '纳斯达克']),
    ('A股', _A_NAMES),
    ('港股', ['恒生指数', '恒生科技', '恒生科技指数']),
    ('日股', ['日经225']),
    ('欧股', ['英国富时100', '富时100']),
    ('商品', ['COMEX黄金', 'NYMEX原油']),
    ('外汇', ['离岸人民币', '美元兑离岸人民币', '美元指数']),
    ('新加坡', ['富时A50', 'A50期指当月连续']),
]

# 站点名称变体 → 报告显示名
_DISPLAY_MAP = {
    '小型纳指当月连续': '纳指期货',
    '小型道指当月连续': '道指期货',
    '美元兑离岸人民币': '离岸人民币',
    'A50期指当月连续': '富时A50',
}


def _region(name):
    for rg, names in _REGION_MAP:
        if name in names:
            return rg
    return '其他'


_reg_items = [(g, _region(g.get('f14') or '')) for g in _global_diff]
_reg_items.sort(key=lambda x: x[1] if x[1] != 'A股' else '~A股')
for g, rg in _reg_items:
    nm, price, chg, pct = g.get('f14'), g.get('f2'), g.get('f4'), g.get('f3')
    if pct is None:
        continue
    nm = _DISPLAY_MAP.get(nm, nm)
    m.append(f'| {rg} | {nm} | {price:.2f} | {chg:+.2f} | {pct:+.2f}% |')
m.append('')

# ── §2 市场情绪 ──
m.append('## 二、市场情绪')
m.append('')
m.append('### 2.1 情绪指标面板')
m.append('')
m.append('')
m.append('| 指标 | 数值 | 指标 | 数值 |')
m.append('|---|---|---|---|')
m.append('')


def _emo(label, key, suf='', signed=False):
    v = EMOTION_NOW.get(key)
    if v is None:
        return f'| {label} | **—** |'
    if isinstance(v, float):
        # HSLN 主力净流入带符号 (历史格式: +495 亿 / -344 亿)
        s = f'{v:+.0f}' if signed else _fmt_pct(v)
    else:
        s = str(v)
    return f'| {label} | **{s}{suf}** |'


panel_rows = [
    ('情绪指标', 'QX', '', False), ('涨停家数', 'ZT', '', False),
    ('跌停家数', 'DT', '', False), ('亏钱效应', 'KQXY', '', False),
    ('主力净流入', 'HSLN', ' 亿', True), ('连板高度', 'LBGD', '', False),
    ('上涨家数', 'SZ', '', False), ('下跌家数', 'XD', '', False),
    ('封板率', 'PB', '%', False), ('昨涨停表现', 'ZTBX', '%', False),
    ('昨连板表现', 'LBBX', '%', False), (None, None, None, None),
]
for i in range(0, len(panel_rows), 2):
    l1, k1, s1, g1 = panel_rows[i]
    l2, k2, s2, g2 = panel_rows[i + 1]
    left = _emo(l1, k1, s1, g1) if l1 else '|  | **—** |'
    right = _emo(l2, k2, s2, g2) if l2 else '|  | **** |'
    m.append(f'{left} {right}')
    m.append('')
m.append('')

# ── 2.2 涨跌停统计 ──
_zt_list = _pool_list('ztpool')
_zb_list = _pool_list('zbpool')
_dt_list = _pool_list('dtpool')
_lb_list = _pool_list('lbpool')
_cz_list = _pool_list('czpool')
_dm_list = _pool_list('dmpool')
_fx_list = _pool_list('fxpool')

_zt_n = len(_zt_list)
_zb_n = len(_zb_list)
_dt_n = len(_dt_list)
_lb_n = len(_lb_list)
_cz_n = len(_cz_list)
_dm_n = len(_dm_list)
_fx_n = len(_fx_list)

# v2.9.18: vision 优先口径 — 2.2 面板 / 复盘总结 / 日志 统一用解析后的家数
# (9/24: pool 涨停 51 只 vs vision 52 家, 总结误显 51 与面板矛盾)
_zt_v = int(_zt or _zt_n)
_dt_v = int(_dt or _dt_n)

_zbr = _zb_n / (_zt_n + _zb_n) * 100 if (_zt_n + _zb_n) else 0
_zbmx = max((int(x[4]) for x in _zb_list if isinstance(x, list) and len(x) > 4), default=0)

m.append('### 2.2 涨跌停统计')
m.append('')
m.append('')
m.append('| 项目 | 今日 | 数据源 |')
m.append('|---|---|---|')
m.append('')


def _stat(label, val, src):
    return f'| {label} | **{val}** | {src} |'


m.append(_stat('涨停家数', _zt_v, 'vision 真实值'))
m.append('')
m.append(_stat('连板家数', _lb_n, 'pool 实时'))
m.append('')
m.append(_stat('炸板', _zb_n, 'pool 实时'))
m.append('')
m.append(_stat('跌停家数', _dt_v, 'vision 真实值'))
m.append('')
m.append(f'| 冲涨 | {_cz_n} | pool 实时 |')
m.append('')
m.append(f'| 大面 | {_dm_n} | pool 实时 |')
m.append('')
m.append(f'| 热门 | {_fx_n} | pool 实时 |')
m.append('')
m.append(_stat('封板率', f'{_fmt_pct(EMOTION_NOW.get("PB"))}%', 'vision 真实值'))
m.append('')
m.append(f'| 炸板率 | **{_zbr:.2f}%** | 实时 |')
m.append('')
m.append(_stat('最高炸板次数', f'{_zbmx}次', 'pool 实时'))
m.append('')
m.append('')

# ── 2.3 连扳梯队 ──
m.append('### 2.3 连扳梯队')
m.append('')
m.append('')
m.append('| 板数 | 股票 | 板块概念 |')
m.append('|---|---|---|')
m.append('')

_lb_rows = []
for x in _lb_list:
    if not isinstance(x, list) or len(x) < 8:
        continue
    try:
        n = int(x[11])
    except (ValueError, IndexError):
        n = 0
    _lb_rows.append((n, x[1], x[0], x[6]))
_lb_rows.sort(key=lambda r: -r[0])
if _lb_rows:
    for n, name, code, concept in _lb_rows:
        m.append(f'| {n}连板 | {name}({code}) | {concept} |')
        m.append('')
else:
    m.append('| — | 无连板股 | — |')
    m.append('')
m.append('')

# ── 2.4 晋级率 ──
m.append('### 2.4 市场晋级率')
m.append('')
m.append('')
m.append('| 晋级路径 | 今日统计 |')
m.append('|---|---|')
m.append('')

_jinji_rows = []
if _jinji:
    html = _jinji.get('html') or ''
    for mm in re.finditer(r'<tr><td>([^<]+)</td><td[^>]*>([^<]+)</td>', html):
        _jinji_rows.append((mm.group(1).strip(), mm.group(2).strip()))


def _jj_key(path):
    mm = re.match(r'(\d+)进(\d+)', path)
    if mm:
        return int(mm.group(1))
    if path == '首板':
        return 99
    return 999


_jinji_rows.sort(key=lambda r: _jj_key(r[0]))
if _jinji_rows:
    for path, stat in _jinji_rows:
        m.append(f'| {path} | {stat} |')
        m.append('')
else:
    m.append('| — | — |')
    m.append('')
m.append('')

# ── 2.5 综合判断 ──
_qx_v = EMOTION_NOW.get('QX')
_zone = '火爆' if (_qx_v or 0) > 80 else '良好' if (_qx_v or 0) > 50 else '一般' if (_qx_v or 0) > 20 else '冰点'
_lbgd = int(EMOTION_NOW.get('LBGD') or 0)
_pb_v = EMOTION_NOW.get('PB')

m.append('### 2.5 综合判断')
m.append('')
m.append(f'- 情绪指标 **{_qx_v:.1f}**，处于「{_zone}」区间')
m.append('')
m.append(f'- 连扳高度：**{_lbgd} 板**')
m.append('')
m.append(f'- 封板率 **{_fmt_pct(_pb_v)}%**')
m.append('')
m.append('')

# ── §3 涨幅排行榜 ──
m.append('## 三、涨幅排行榜')
m.append('')
m.append('### 3.1 当日涨幅 TOP15（涨停池内）')
m.append('')
m.append('')
m.append('| # | 名称 | 代码 | 涨幅 | 板数 | 成交额 | 概念 |')
m.append('|---|---|---|---|---|---|')
m.append('')

_zt_sorted = sorted([x for x in _zt_list if isinstance(x, list) and len(x) > 8],
                    key=lambda x: -(float(x[2]) if str(x[2]).replace('.', '', 1).replace('-', '', 1).isdigit() else 0))
for i, x in enumerate(_zt_sorted[:15], 1):
    code, name, pct = x[0], x[1], x[2]
    ban, amount, concept = x[7], x[3], x[6]
    m.append(f'| {i} | {name} | {code} | **{_fmt_pct(pct)}%** | {ban} | {_fmt_amount_wan(amount)} | {concept} |')
    m.append('')
m.append('')

# ── 3.2 成交额 TOP10 ──
m.append('### 3.2 成交额 TOP10（涨停池内）')
m.append('')
m.append('')
m.append('| # | 名称 | 代码 | 成交额 | 涨幅 | 概念 |')
m.append('|---|---|---|---|---|---|')
m.append('')

_amt_sorted = sorted([x for x in _zt_list if isinstance(x, list) and len(x) > 8],
                     key=lambda x: -(float(x[3]) if str(x[3]).replace('.', '', 1).replace('-', '', 1).isdigit() else 0))
for i, x in enumerate(_amt_sorted[:10], 1):
    code, name, pct, amount, concept = x[0], x[1], x[2], x[3], x[6]
    m.append(f'| {i} | {name} | {code} | **{_fmt_amount_wan(amount)}** | +{_fmt_pct(pct)}% | {concept} |')
    m.append('')
m.append('')

# ── §4 市场题材全景图 ──
_zs = None
for cand in (os.path.join(DESKTOP, 'zthis_sectors.json'), os.path.join(SCRIPT_DIR, 'zthis_sectors.json')):
    if os.path.isfile(cand):
        try:
            _zs = json.load(open(cand, encoding='utf-8'))
            break
        except Exception:
            pass

_sectors = (_zs or {}).get('sectors') or []
# v2.9.2: 按涨停数降序 (zthis json 页面顺序 ≠ 报告热度顺序)
_sectors.sort(key=lambda s: -(s.get('zt_count') or 0))
# 全量渲染 (标题"TOP13"为历史遗留名, 板块 >13 时渲染全部 — 8/28 14板块版先例)
_top13 = _sectors

m.append('## 四、市场题材全景图')
m.append('')
m.append('> 【热门板块 TOP13】数据源: 涨停表现页 /web/zthis (vision 招牌 + DOM 实拍)')
m.append('')
m.append('')
m.append('### 4.1 涨停题材热度 TOP13')
m.append('')
m.append('')
m.append('| # | 板块 | 板块涨幅 | 涨停数 | 代表股 |')
m.append('|---|---|---|---|---|')
m.append('')

for i, s in enumerate(_top13, 1):
    name = s.get('name') or '—'
    pct = s.get('pct')
    cnt = s.get('zt_count') or 0
    reps = ' / '.join(f"{st.get('name')}({st.get('code')})" for st in (s.get('stocks') or [])[:5])
    m.append(f'| {i} | {name} | {_fmt_pct(pct)}% | **{cnt}** | {reps} |')
    m.append('')
m.append('')

# ── 4.2 板块代表股详细数据 (15 字段, v2.9.3) ──
m.append('### 4.2 板块代表股详细数据 (15 字段)')
m.append('')
m.append('')
m.append('> 数据源: 涨停表现页 /web/zthis (DOM 实拍 · 完整详细字段) | opencli 全量采集 (无 9 row 截断限制)')
m.append('')
m.append('| 名称 | 代码 | 现涨幅 | 昨收价 | 板数 | 连板 | 板形 | 首封 | 终封 | 成交额 | 实际流通 | 总市值 | 换手率 | 异动原因 | 龙虎榜 |')
m.append('')
m.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
m.append('')

_F15 = ['name', 'code', 'pct_chg', 'pre_close', 'ban', 'lianban', 'board_type',
        'first_limit', 'last_limit', 'amount', 'free_cap', 'total_cap',
        'turnover', 'reason', 'dragon_tiger']
for i, s in enumerate(_top13, 1):
    name = s.get('name') or '—'
    pct = s.get('pct')
    cnt = s.get('zt_count') or 0
    m.append(f'#### {i}. {name} ({_fmt_pct(pct)}% | **{cnt} 涨停)')
    m.append('')
    m.append('')
    for st in (s.get('stocks') or []):
        vals = [st.get(h, '') for h in _F15]
        m.append('| ' + ' | '.join(str(v) for v in vals) + ' |')
        m.append('')
    m.append('')
    m.append('')

# ── 4.3 主线题材结构图 (mermaid) ──
m.append('### 4.3 主线题材结构图')
m.append('```mermaid')
m.append('graph TD')
m.append('')
for i, s in enumerate(_top13[:9], 1):
    nm = s.get('name') or '—'
    cnt = s.get('zt_count') or 0
    m.append(f'  {chr(64 + i)}[{nm}<br/>{cnt}涨停] --> {chr(64 + i)}1[涨停龙头]')
m.append('')
m.append('```')
m.append('')
m.append('')

# ── §5 板块涨跌幅 TOP10 ──
m.append('## 五、板块涨跌幅 TOP10')
m.append('')
m.append('')
m.append('### 5.1 涨幅 TOP10（按涨停数排序）')
m.append('')
m.append('')
m.append('| # | 板块 | 板块涨幅 | 涨停数 | 代表股 |')
m.append('|---|---|---|---|---|')
m.append('')

for i, s in enumerate(_sectors[:10], 1):
    name = s.get('name') or '—'
    pct = s.get('pct')
    cnt = s.get('zt_count') or 0
    reps = ' / '.join(st.get('name') or '' for st in (s.get('stocks') or [])[:3])
    m.append(f'| {i} | {name} | {_fmt_pct(pct)}% | **{cnt}** | {reps} |')
    m.append('')
m.append('')

m.append('')
m.append('### 5.2 跌幅 TOP10（按跌停数反推）')
m.append('')
m.append('')
m.append('| # | 板块 | 跌停数 | 代表股 |')
m.append('|---|---|---|---|')
m.append('')

_dt_concepts = Counter()
for x in _dt_list:
    if isinstance(x, list) and len(x) > 6 and x[6]:
        _dt_concepts[x[6].split('+')[0].strip()] += 1
if _dt_concepts:
    for i, (c, n) in enumerate(_dt_concepts.most_common(10), 1):
        m.append(f'| {i} | {c} | **{n}** | — |')
        m.append('')
else:
    m.append('| 1 | 今日无跌停票 | **0** | — |')
    m.append('')
m.append('')

# ── §6 主力资金 ──
m.append('## 六、主力资金净流入/净流出 TOP10')
m.append('')
m.append('> 数据源：涨停池题材反推（无板块级资金接口）。')
m.append('')
m.append('')
m.append('### 6.1 净流入候选 TOP10（涨停驱动）')
m.append('')
m.append('')
m.append('| # | 题材 | 涨停数 | 推断 |')
m.append('|---|---|---|---|')
m.append('')

for i, s in enumerate(_sectors[:10], 1):
    name = s.get('name') or '—'
    cnt = s.get('zt_count') or 0
    m.append(f'| {i} | {name} | **{cnt}** | 涨停驱动 |')
    m.append('')
m.append('')

m.append('')
m.append('### 6.2 净流出候选 TOP10（跌停驱动）')
m.append('')
m.append('')
m.append('| # | 题材 | 跌停数 | 推断 |')
m.append('|---|---|---|---|')
m.append('')

if _dt_concepts:
    for i, (c, n) in enumerate(_dt_concepts.most_common(10), 1):
        m.append(f'| {i} | {c} | **{n}** | 跌停驱动 |')
        m.append('')
else:
    m.append('| 1 | 今日无跌停票 | **0** | 跌停驱动 |')
    m.append('')
m.append('')

# ── 附录 A：跌停股明细 ──
m.append('## 附录 A：跌停股明细')
m.append('')
m.append('')
m.append('| 名称 | 代码 | 跌幅 |')
m.append('|---|---|---|')
m.append('')

if _dt_list:
    for x in _dt_list:
        if not isinstance(x, list) or len(x) < 3:
            continue
        m.append(f'| {x[1]} | {x[0]} | **{_fmt_pct(x[2])}%** |')
        m.append('')
else:
    m.append('| 今日无跌停票 | — | — |')
    m.append('')
m.append('')

# ── 附录 B：今日炸板 TOP ──
m.append('## 附录 B：今日炸板 TOP')
m.append('')
m.append('')
m.append('| 名称 | 代码 | 涨幅 | 炸板次数 | 成交额 |')
m.append('|---|---|---|---|---|')
m.append('')

# zbpool: [code,name,pct,"",次数,time,concept,"",free_cap,total_cap] — 无成交额时显示 —
# 历史版本元素 >10 且 idx10 为数字时视为成交额
for x in sorted(_zb_list, key=lambda v: -(int(v[4]) if isinstance(v, list) and len(v) > 4 and str(v[4]).isdigit() else 0)):
    if not isinstance(x, list) or len(x) < 5:
        continue
    amt = ''
    if len(x) > 10 and str(x[10]).replace('.', '', 1).isdigit():
        amt = _fmt_amount_wan(x[10])
    m.append(f'| {x[1]} | {x[0]} | {_fmt_pct(x[2])}% | {x[4]}次 | {amt} |')
    m.append('')
m.append('')

# ── 成交额可视化 (xychart, v2.9.18 修复: 原 f-string 花括号内含逗号 → 被解析成元组) ──
_names = [x[1] for x in _amt_sorted[:10]]
_vals = [f'{(float(x[3]) / 1e8):.1f}' for x in _amt_sorted[:10]]
m.append('### 成交额可视化')
m.append('```mermaid')
m.append('xychart-beta')
m.append('')
m.append('    title "成交额 TOP10（亿元）"')
m.append('')
_xaxis = ', '.join(f'"{n}"' for n in _names)
_bars = ', '.join(_vals)
m.append(f'    x-axis [{_xaxis}]')
m.append('')
m.append(f'    bar [{_bars}]')
m.append('')
m.append('```')
m.append('')
m.append('')

# ── 复盘总结 ──
_top_s = _sectors[0] if _sectors else None
m.append('## 📝 复盘总结')
m.append('')
if _top_s:
    m.append(f'**主线判断**：{_top_s.get("name")}（{_top_s.get("zt_count")}涨停）领涨，涨停 {_zt_v} 家。')
else:
    m.append(f'**主线判断**：涨停 {_zt_v} 家。')
m.append('')
m.append(f'**情绪周期**：情绪指标 {_qx_v:.1f}（{_zone}区间），封板率 {_fmt_pct(_pb_v)}%，连扳高度 {_lbgd} 板。')
m.append('')
m.append(f'**赚钱效应**：涨停 {_zt_v} / 跌停 {_dt_v} / 炸板 {_zb_n}。')
m.append('')
m.append('')
m.append('---')
m.append('')
m.append('> 📌 本报告由花花自动化生成（v2.9.0 rebuild）。')
m.append('')
m.append('> 数据全部从 [短线侠](https://duanxianxia.cn/web/main) 10 个 JSON 端点实时抓取。')
m.append('')

# ── 写盘 ──
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, f'{DATE_STR.replace("-", "")}_收盘复盘.md')
content = '\n'.join(m)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'✅ 报告产出: {out_path}')
print(f'   大小: {len(content):,} 字符 · {len(m)} 行')
print(f'[fupan] 涨停{_zt_v} 跌停{_dt_v} 连扳{_lb_n} 封板率{(_zt_n / (_zt_n + _zb_n) * 100 if (_zt_n + _zb_n) else 0):.2f}%')
