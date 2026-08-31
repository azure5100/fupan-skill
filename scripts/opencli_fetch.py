# -*- coding: utf-8 -*-
"""
opencli_fetch.py - fupan v2.9.5 opencli 浏览器通道采集器

通过 opencli daemon (127.0.0.1:19825 /command API) 驱动真实 Chrome 采集:
  - vision 模式: /web/main → #qxiframe 11 个情绪按钮 → vision_snap_{BJT}.txt
  - zthis 模式:  /web/zthis → 点 #showhide 全部展开 → 全量解析 → Desktop/zthis_sectors.json

前置条件: opencli doctor 显示 [OK] Daemon + [OK] Extension connected
  (Chrome 需打开且 opencli 扩展已连接)

用法:
  python opencli_fetch.py vision        # 生成 vision_snap_{YYYY-MM-DD}.txt (scripts/ 下)
  python opencli_fetch.py zthis         # 生成 Desktop/zthis_sectors.json (全量 15 板块)
  python opencli_fetch.py check         # 桥接自检

2026-08-05 实测: 15 板块 / 103 股全量采集, 无 9 row 截断限制。
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

DAEMON = 'http://127.0.0.1:19825/command'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\cosmo'), 'Desktop')
BJT = timezone(timedelta(hours=8))
BJT_TODAY = datetime.now(BJT).strftime('%Y-%m-%d')

_tab_id = None


def send(action, params=None, retries=3):
    """POST /command, 返回 data (可能是 JSON 字符串, 调用方自行 parse)"""
    cmd = {'id': f'cmd_{int(time.time()*1000)}', 'action': action}
    if params:
        cmd.update(params)
    if _tab_id is not None:
        cmd.setdefault('tabId', _tab_id)
    cmd.setdefault('workspace', 'default')
    body = json.dumps(cmd).encode('utf-8')
    req = urllib.request.Request(DAEMON, data=body,
                                 headers={'Content-Type': 'application/json', 'X-OpenCLI': '1'})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.loads(r.read().decode('utf-8'))
            if not res.get('ok'):
                raise RuntimeError(res.get('error', 'daemon command failed'))
            return res.get('data')
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5)


def navigate(url):
    global _tab_id
    res = send('navigate', {'url': url})
    _tab_id = res.get('tabId') if isinstance(res, dict) else None
    print(f'[opencli] navigated → {url} (tabId={_tab_id})')
    time.sleep(2.5)  # SPA 渲染


def exec_js(code):
    return send('exec', {'code': code})


def check():
    import urllib.error
    try:
        req = urllib.request.Request('http://127.0.0.1:19825/status', headers={'X-OpenCLI': '1'})
        with urllib.request.urlopen(req, timeout=3) as r:
            st = json.loads(r.read().decode('utf-8'))
        print(f"[opencli] daemon OK, extensionConnected={st.get('extensionConnected')}")
        return bool(st.get('extensionConnected'))
    except urllib.error.URLError:
        print('[opencli] daemon 未运行 (opencli doctor 诊断)')
        return False


# ─── vision 模式: /web/main → #qxiframe 11 情绪按钮 ───
EMOTION_LABELS = ['情绪指标', '涨停家数', '跌停家数', '亏钱效应', '主力流入', '连板高度',
                  '上涨家数', '下跌家数', '今日封板率', '昨涨停表现', '昨连板表现']


def fetch_vision():
    navigate('https://duanxianxia.cn/web/main')
    code = """(() => {
      const f = document.getElementById('qxiframe');
      if (!f || !f.contentDocument) return JSON.stringify({err: 'no qxiframe'});
      const doc = f.contentDocument;
      const out = [];
      for (const b of doc.querySelectorAll('button')) {
        const t = (b.textContent || '').trim();
        if (/^(情绪指标|涨停家数|跌停家数|亏钱效应|主力流入|连板高度|上涨家数|下跌家数|今日封板率|昨涨停表现|昨连板表现)[：:]/.test(t)) {
          out.push(t);
        }
      }
      return JSON.stringify({buttons: out});
    })()"""
    data = exec_js(code)
    data = json.loads(data) if isinstance(data, str) else data
    btns = data.get('buttons', [])
    if len(btns) < 11:
        print(f'[opencli] FATAL: 只找到 {len(btns)} 个情绪按钮 (期望 11), 请确认页面已刷新')
        sys.exit(1)
    # 按 EMOTION_LABELS 顺序重排 (DOM 顺序可能不同)
    def key_of(t):
        for i, lab in enumerate(EMOTION_LABELS):
            if t.startswith(lab):
                return i
        return 99
    btns.sort(key=key_of)
    # SKILL.md A1 铁律: HSLN (主力流入) 必须去"亿"单位 — 否则 float('-383亿') → ValueError
    btns = [t.replace('亿', '') if t.startswith('主力流入') else t for t in btns]
    lines = [f'button "{t}"' for t in btns]
    snap_path = os.path.join(SCRIPT_DIR, f'vision_snap_{BJT_TODAY.replace("-", "")}.txt')
    with open(snap_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[opencli] vision snapshot 已写: {snap_path} ({len(btns)} 项)')
    for l in lines[:4]:
        print(f'  {l}')


# ─── zthis 模式: /web/zthis 全量采集 → zthis_sectors.json ───
ZTHIS_HEADERS = ['name', 'code', 'pct_chg', 'pre_close', 'ban', 'lianban', 'board_type',
                 'first_limit', 'last_limit', 'amount', 'free_cap', 'total_cap',
                 'turnover', 'reason', 'dragon_tiger']


def fetch_zthis():
    navigate('https://duanxianxia.cn/web/zthis')
    # 1. 点"全部展开" (必须 button#showhide 本体)
    code = """(() => {
      const btn = document.getElementById('showhide');
      if (!btn) return JSON.stringify({err: 'no showhide button'});
      ['mousedown','mouseup','click'].forEach(evt =>
        btn.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window})));
      return JSON.stringify({clicked: true});
    })()"""
    r = exec_js(code)
    print(f'[opencli] 全部展开: {r}')
    time.sleep(2.5)
    # 2. 全量解析 .ztitem(板块标题) ↔ .zt(table.ztlist) 配对
    code = """(() => {
      const headers = ["name","code","pct_chg","pre_close","ban","lianban","board_type","first_limit","last_limit","amount","free_cap","total_cap","turnover","reason","dragon_tiger"];
      const list = document.getElementById('ztlist');
      if (!list) return JSON.stringify({err: 'no #ztlist'});
      const sectors = [];
      for (const k of list.children) {
        if (!k.classList.contains('ztitem')) continue;
        const raw = (k.innerText || '').trim().split('\\n').map(s=>s.trim()).filter(Boolean);
        const m = (raw[0] || '').match(/^(.+?)（(-?[\\d.]+)%）$/);
        const table = k.nextElementSibling && k.nextElementSibling.querySelector
          ? k.nextElementSibling.querySelector('table.ztlist') : null;
        const stocks = [];
        if (table) {
          for (let r = 1; r < table.rows.length; r++) {
            const cells = [...table.rows[r].cells].map(c => (c.innerText||'').trim());
            const st = {};
            headers.forEach((h, i) => st[h] = cells[i] || '');
            stocks.push(st);
          }
        }
        sectors.push({name: m ? m[1] : raw[0], pct: m ? parseFloat(m[2]) : null,
                      zt_count: parseInt(raw[1] || '0', 10) || 0, stocks});
      }
      return JSON.stringify({sectorCount: sectors.length,
        totalStocks: sectors.reduce((a,s)=>a+s.stocks.length,0), sectors});
    })()"""
    data = exec_js(code)
    data = json.loads(data) if isinstance(data, str) else data
    if data.get('err'):
        print(f'[opencli] FATAL: {data["err"]}')
        sys.exit(1)
    out = {'date': BJT_TODAY, 'source': 'opencli DOM snapshot (全量, 无 9 row 截断)', 'sectors': data['sectors']}
    # v2.9.8: 双份保存 — Desktop (gen_report 主读) + scripts (缓存兜底, 防 Desktop 被清后 §4 空)
    for path in (os.path.join(DESKTOP, 'zthis_sectors.json'),
                 os.path.join(SCRIPT_DIR, 'zthis_sectors.json')):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    print(f'[opencli] zthis_sectors.json 已写: Desktop + scripts ({data["sectorCount"]} 板块 / {data["totalStocks"]} 股)')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == 'check':
        check()
        return
    if not check():
        sys.exit(1)
    if mode == 'vision':
        fetch_vision()
    elif mode == 'zthis':
        fetch_zthis()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
