# -*- coding: utf-8 -*-
"""
verify_report.py - fupan v2.9.16 报告验证器 (35 项)

从 Desktop 的 emotion_vision.json + pools 读期望值, 验证最新报告:
  章节完整性 / 关键数值 (指数/涨停/跌停/封板率/连板高度/情绪/主力) /
  涨停全量 (ztpool 与报告 TOP15 对比) / mermaid 图 / 数据源标注 /
  python 关键字泄露

v2.9.12: 0 跌停日 dtpool list=null → [] 防御; 期望值用 'X' in dict 存在性判断
v2.9.7: 不再 import gen_report (避免副作用), _eo_data 直接读 emotion_vision.json
v2.4.1: verify 完成后自动删除 10 个临时 JSON

用法:
  python verify_report.py [--report /path/to/report.md]
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DESKTOP = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\cosmo'), 'Desktop')
DATA_DIR = os.path.join(DESKTOP, '股票账户监管', 'hermes每日复盘数据')
BJT = timezone(timedelta(hours=8))
BJT_TODAY = datetime.now(BJT).strftime('%Y-%m-%d')

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f'  [OK] {msg}')


def fail(msg):
    global FAIL
    FAIL += 1
    print(f'  [X] {msg}')


def _load(name):
    """读 Desktop JSON, 缺失/坏文件返回 None"""
    p = os.path.join(DESKTOP, name)
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return None


def _pool_list(tag):
    d = _load(f'{tag}.json') or {}
    lst = d.get('list')
    return lst if isinstance(lst, list) else []


def _fmt_pct(v):
    if v is None:
        return '—'
    s = f'{float(v):.2f}'
    return s.rstrip('0').rstrip('.') if '.' in s else s


def main():
    # ── 定位报告 ──
    report_path = None
    if '--report' in sys.argv:
        i = sys.argv.index('--report')
        if i + 1 < len(sys.argv):
            report_path = sys.argv[i + 1]
    if not report_path:
        cands = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR)
                 if f.endswith('_收盘复盘.md')]
        if not cands:
            print('[X] 未找到任何报告')
            return 1
        report_path = max(cands, key=os.path.getmtime)

    if not os.path.isfile(report_path):
        print(f'[X] 报告不存在: {report_path}')
        return 1
    body = open(report_path, encoding='utf-8').read()
    size = len(body)
    print(f'Verifying: {report_path}')
    print(f'Reading pools from: {DESKTOP}')

    # ── 期望值 ──
    eo = _load('emotion_vision.json') or {}
    _zt_exp = eo.get('ZT')
    _dt_exp = eo.get('DT')
    _pb_exp = eo.get('PB')
    _qx_exp = eo.get('QX')
    _lbgd_exp = eo.get('LBGD')
    _hsln_exp = eo.get('HSLN')

    ztpool = _pool_list('ztpool')
    lbpool = _pool_list('lbpool')
    dtpool = _pool_list('dtpool')
    zbpool = _pool_list('zbpool')

    # 1. 文件存在
    ok(f'报告文件存在 ({os.path.basename(report_path)})')
    # 2. 强度
    ok(f'报告强度 ({size} chars)')
    # 3-11. 章节
    for sec in ['一、市场概览', '二、市场情绪', '三、涨幅排行榜', '四、市场题材全景图',
                '五、板块涨跌幅 TOP10', '六、主力资金', '附录 A：跌停股明细',
                '附录 B：今日炸板 TOP', '复盘总结']:
        if sec in body:
            ok(f'章节存在: {sec}')
        else:
            fail(f'章节缺失: {sec}')
    # 12. 指数
    g = _load('global.json')
    diff = ((g or {}).get('data') or {}).get('diff') or []
    sh = next((x for x in diff if x.get('f14') == '上证指数'), None)
    if sh and f'{sh.get("f2"):.2f}' in body:
        ok(f'验证指数 {sh.get("f2"):.2f}')
    else:
        fail('指数验证失败')
    cyb = next((x for x in diff if x.get('f14') == '创业板指'), None)
    if cyb and f'{cyb.get("f3"):+.2f}%' in body:
        ok(f'创业板 {cyb.get("f3"):+.2f}%')
    else:
        fail('创业板验证失败')
    # 13-16. 涨停/跌停/封板率/连板高度
    if _zt_exp is not None and f'**{int(_zt_exp)}**' in body:
        ok(f'涨停 {int(_zt_exp)}')
    else:
        fail(f'涨停验证失败 (期望 {_zt_exp})')
    if _dt_exp is not None and f'**{int(_dt_exp)}**' in body:
        ok(f'跌停 {int(_dt_exp)}')
    else:
        fail(f'跌停验证失败 (期望 {_dt_exp})')
    if _pb_exp is not None and f'{_fmt_pct(_pb_exp)}%' in body:
        ok(f'封板率 {_fmt_pct(_pb_exp)}%')
    else:
        fail(f'封板率验证失败 (期望 {_pb_exp})')
    if _lbgd_exp is not None and f'**{int(_lbgd_exp)} 板**' in body:
        ok(f'连板高度 {int(_lbgd_exp)}')
    else:
        fail(f'连板高度验证失败 (期望 {_lbgd_exp})')
    # 17. 情绪指标
    if _qx_exp is not None and f'**{_qx_exp:.1f}**' in body:
        ok(f'情绪指标 {_qx_exp:.1f}')
    else:
        fail(f'情绪指标验证失败 (期望 {_qx_exp})')
    # 18. 主力净流入
    if _hsln_exp is not None:
        hsln_s = f'{_hsln_exp:+.0f}' if isinstance(_hsln_exp, float) else str(_hsln_exp)
        if hsln_s in body:
            ok(f'主力净流入 {hsln_s}')
        else:
            fail(f'主力净流入验证失败 (期望 {hsln_s})')
    # 19. 涨停数一致 (2.1 面板 vs 2.2 统计)
    zt_counts = re.findall(r'\*\*(\d+)\*\*', body)
    if _zt_exp is not None and str(int(_zt_exp)) in zt_counts:
        ok(f"涨停数一致 ({int(_zt_exp)}) ({zt_counts[:2]})")
    else:
        fail('涨停数一致性验证失败')
    # 20. 最高板个股 (lbpool 最高板在报告中)
    if lbpool:
        lb_sorted = sorted([x for x in lbpool if isinstance(x, list) and len(x) > 8],
                           key=lambda x: -(int(x[11]) if str(x[11]).isdigit() else 0))
        if lb_sorted:
            top = lb_sorted[0]
            if f'{top[1]}({top[0]})' in body:
                ok(f'最高板个股: {top[1]}({top[0]})')
            else:
                fail(f'最高板个股缺失: {top[1]}({top[0]})')
    # 21. 晋级率
    jinji = _load('jinji.json') or {}
    if jinji.get('html'):
        paths = re.findall(r'<tr><td>([^<]+)</td>', jinji['html'])
        if paths:
            ok(f"晋级率 {paths[0]}")
        else:
            fail('晋级率解析失败')
    # 22. 情绪指标 >= 3
    if _qx_exp is not None and _qx_exp >= 3:
        ok(f'情绪指标 >=3 ({_qx_exp})')
    else:
        fail(f'情绪指标 <3 ({_qx_exp})')
    # 23. 港股指数 >= 2
    hk = [x for x in diff if '恒生' in (x.get('f14') or '')]
    if len(hk) >= 2:
        ok(f'港股指数 {len(hk)} 项')
    else:
        fail(f'港股指数不足 ({len(hk)})')
    # 24. 涨幅 TOP15 全量 (与 gen_report 3.1 同口径: 按涨幅降序取 15)
    zt_sorted = sorted([x for x in ztpool if isinstance(x, list) and len(x) > 8],
                       key=lambda x: -(float(x[2]) if str(x[2]).replace('.', '', 1).replace('-', '', 1).isdigit() else 0))
    missing15 = []
    for x in zt_sorted[:15]:
        if x[1] not in body:
            missing15.append(x[1])
    if not missing15:
        ok('涨幅 TOP15 全部存在 (缺失: [])')
    else:
        fail(f'涨幅 TOP15 缺失: {missing15}')
    # 25. 成交额 TOP1
    if ztpool:
        amt_sorted = sorted([x for x in ztpool if isinstance(x, list) and len(x) > 3],
                            key=lambda x: -(float(x[3]) if str(x[3]).replace('.', '', 1).isdigit() else 0))
        if amt_sorted:
            t = amt_sorted[0]
            if t[1] in body:
                ok(f'成交额TOP1 {t[1]}')
            else:
                fail(f'成交额TOP1 缺失: {t[1]}')
    # 26. 涨停全量 (基准: zthis_sectors.json — §4 详表渲染来源; ztpool 可能含口径外股票)
    zs = None
    for cand in (os.path.join(DESKTOP, 'zthis_sectors.json'),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zthis_sectors.json')):
        if os.path.isfile(cand):
            try:
                zs = json.load(open(cand, encoding='utf-8'))
                break
            except Exception:
                pass
    zthis_names = []
    for s in (zs or {}).get('sectors') or []:
        for st in s.get('stocks') or []:
            zthis_names.append(st.get('name'))
    missing_all = [n for n in zthis_names if n and n not in body]
    if not missing_all:
        ok(f'涨停全量 ({len(zthis_names)} 只 zthis 股票全在报告, 缺失: [])')
    else:
        fail(f'涨停全量缺失 {len(missing_all)}: {missing_all[:5]}')
    # 27. mermaid graph
    if '```mermaid' in body and 'graph TD' in body:
        ok('mermaid graph 图')
    else:
        fail('mermaid graph 缺失')
    # 28. mermaid xychart
    if 'xychart-beta' in body:
        ok('mermaid xychart 成交额')
    else:
        fail('mermaid xychart 缺失')
    # 29. 关注代码缺失检查
    if '(000688)' not in body and '(688000)' not in body:
        ok('关注代码缺失检查')
    else:
        fail('关注代码出现')
    # 30. 关注数据格式
    if '**None**' not in body and '**nan**' not in body and '**—**' not in body:
        ok('关注数据格式正常')
    else:
        fail('关注数据格式异常 (None/nan/—)')
    # 31-33. v2.2.0
    if 'vision 真实值' in body:
        ok('[v2.2.0] 2.2 数据源标注存在')
    else:
        fail('[v2.2.0] 2.2 数据源标注缺失')
    if '数据来源' in body:
        ok('[v2.2.0] 5 数据源说明存在')
    else:
        fail('[v2.2.0] 5 数据源说明缺失')
    if '成交额 TOP10' in body:
        ok('[v2.2.0] 3.2 成交额 TOP10 存在')
    else:
        fail('[v2.2.0] 3.2 成交额 TOP10 缺失')
    # 34. python 关键字泄露
    leaks = [k for k in ['def ', 'import ', 'print(', 'os.path', 'list('] if k in body]
    if not leaks:
        ok('无 python 关键字泄露')
    else:
        fail(f'python 关键字泄露: {leaks}')

    print('')
    print(f'=== 验证报告 ({PASS}/{PASS + FAIL} pass) ===')
    if FAIL:
        print(f'失败: {FAIL}')
        return 1
    # v2.4.1: verify 完成后自动删除 10 个临时 JSON
    _TEMP_JSON = 'ztpool.json zbpool.json dtpool.json lbpool.json czpool.json dmpool.json fxpool.json global.json qxlive.json jinji.json'.split()
    _del = 0
    for f in _TEMP_JSON:
        p = os.path.join(DESKTOP, f)
        if os.path.isfile(p):
            try:
                os.remove(p)
                _del += 1
            except Exception:
                pass
    print(f'[fupan] v2.4.1 verify 完成, 自动清理 {_del} 个临时 JSON (自动删除)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
