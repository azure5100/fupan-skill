#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fupan_oneclick.py - fupan v2.9.6 一键复盘 (采集 → 生成 → 验证)

流程 (当日模式):
  1. opencli 桥接检查 (未连则自动拉起 Chrome + opencli 扩展)
  2. opencli_fetch.py vision  → scripts/vision_snap_{YYYYMMDD}.txt (11 项情绪)
  3. opencli_fetch.py zthis   → Desktop/zthis_sectors.json (15 板块全量)
  4. fupan_run.py --vision-snapshot (Step0 清残留 → 拉数据 → gen_report → verify)

用法:
  python fupan_oneclick.py                     # 当日完整流程 (收盘后跑)
  python fupan_oneclick.py --date 2026-08-05   # 补生成历史报告 (跳过采集, 用已有 snapshot)
  python fupan_oneclick.py --skip-verify       # 跳过验证 (调试用)

前置: 已安装 opencli (@jackwener/opencli) + Chrome; 当日模式需 Chrome 可拉起
注意: 当日模式会在跑前强制采集最新 snapshot —— 若短线侠未刷新 (凌晨/周末),
      生成的是最近交易日数据, 报告 header 日期 = BJT today (跨日需用 --date)。
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\cosmo'), 'Desktop')
BJT = timezone(timedelta(hours=8))
BJT_TODAY = datetime.now(BJT).strftime('%Y-%m-%d')
PY = sys.executable or 'python'

# 让所有子进程 UTF-8 输出 (Windows GBK 控制台会因 ✅ emoji 崩溃)
os.environ['PYTHONIOENCODING'] = 'utf-8'
# 本进程 stdout 也切 UTF-8 (v2.9.8: 补生成模式直接 print gen_report 的 ✅ 输出会 GBK 崩)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DAEMON_URL = 'http://127.0.0.1:19825'
CHROME_CANDIDATES = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.join(os.environ.get('LOCALAPPDATA', r'C:\Users\cosmo\AppData\Local'),
                 'Google', 'Chrome', 'Application', 'chrome.exe'),
]
CHROME = next((c for c in CHROME_CANDIDATES if os.path.isfile(c)), None)
OPENCLI_EXT = r'C:\Users\cosmo\.npm-global\node_modules\@jackwener\opencli\extension'
OPENCLI_CMD = r'C:\Users\cosmo\.npm-global\opencli.cmd'  # 冷启动 daemon 用 (CLI lazy 启动)


def log(msg):
    print(f'[oneclick {datetime.now(BJT).strftime("%H:%M:%S")}] {msg}')


def run(cmd, cwd=None, timeout=300):
    log(f'$ {" ".join(cmd)}')
    r = subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip())
    if r.returncode != 0:
        log(f'[X] 失败 (exit={r.returncode})')
    return r.returncode


def daemon_up():
    """daemon HTTP 可达 (无论扩展是否连接)"""
    try:
        req = urllib.request.Request(f'{DAEMON_URL}/status', headers={'X-OpenCLI': '1'})
        with urllib.request.urlopen(req, timeout=3) as r:
            json.loads(r.read().decode('utf-8'))
        return True
    except Exception:
        return False


def bridge_status():
    """daemon + 扩展全部就绪"""
    try:
        req = urllib.request.Request(f'{DAEMON_URL}/status', headers={'X-OpenCLI': '1'})
        with urllib.request.urlopen(req, timeout=3) as r:
            st = json.loads(r.read().decode('utf-8'))
        return st.get('extensionConnected', False)
    except Exception:
        return False


def ensure_bridge():
    """daemon + 扩展两阶段拉起: ①daemon 未响应 → opencli doctor lazy 启动 ②扩展未连 → Chrome --load-extension"""
    if bridge_status():
        log('opencli 桥接 OK (daemon + 扩展已连接)')
        return True
    # 阶段 ①: daemon 未运行 (8/6 实测: 冷启动时 /status 不通, 直接拉 Chrome 没用)
    if not daemon_up():
        log('opencli daemon 未响应, 尝试拉起 (opencli doctor lazy 启动)...')
        try:
            subprocess.run([OPENCLI_CMD, 'doctor'], capture_output=True, timeout=60,
                           text=True, encoding='utf-8', errors='replace')
        except Exception:
            pass
        for _ in range(10):
            time.sleep(2)
            if daemon_up():
                log('daemon 已拉起')
                break
        if not daemon_up():
            log('[X] daemon 拉起失败 — 手动跑 opencli doctor 诊断')
            return False
    # 阶段 ②: 扩展未连接 → 拉起 Chrome (--load-extension)
    log('opencli 扩展未连接, 尝试拉起 Chrome...')
    if not os.path.isfile(CHROME):
        log(f'[X] Chrome 不存在: {CHROME}, 请手动打开 Chrome 后重试')
        return False
    subprocess.Popen([CHROME, f'--load-extension={OPENCLI_EXT}',
                      'https://duanxianxia.cn/web/main'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(15):  # 最多等 30s (首次扩展握手较慢)
        time.sleep(2)
        if bridge_status():
            log('Chrome 拉起成功, 扩展已连接')
            return True
    log('[X] 等待 30s 扩展仍未连接 — 手动跑 opencli doctor 诊断')
    return False


def main():
    argv = sys.argv[1:]
    forced_date = None
    skip_verify = False
    for i, a in enumerate(argv):
        if a == '--date' and i + 1 < len(argv):
            forced_date = argv[i + 1]
        if a == '--skip-verify':
            skip_verify = True

    # ── 补生成模式: 跳过采集 (需已有该日 snapshot), 走 gen_report --date + verify
    if forced_date:
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', forced_date):
            log(f'[X] --date 格式须 YYYY-MM-DD: {forced_date}')
            sys.exit(1)
        snap = os.path.join(SCRIPT_DIR, f'vision_snap_{forced_date.replace("-", "")}.txt')
        if not os.path.isfile(snap):
            log(f'[X] 补生成需已有 snapshot: {snap} 不存在 — 该日 snapshot 无法重采')
            sys.exit(1)
        log(f'=== 补生成模式: {forced_date} (跳过采集) ===')
        rc = run([PY, os.path.join(SCRIPT_DIR, 'gen_report.py'),
                  '--date', forced_date, '--vision-snapshot', snap])
        if rc != 0:
            sys.exit(rc)
        if not skip_verify:
            rc = run([PY, os.path.join(SCRIPT_DIR, 'verify_report.py')])
        sys.exit(rc)

    # ── 当日模式: 桥接 → 采集 → 主编排 ──
    log(f'=== 当日模式: {BJT_TODAY} ===')
    if not ensure_bridge():
        sys.exit(1)

    log('Step 1: 采集 vision snapshot (11 项情绪)')
    rc = run([PY, os.path.join(SCRIPT_DIR, 'opencli_fetch.py'), 'vision'])
    if rc != 0:
        sys.exit(rc)
    snap = os.path.join(SCRIPT_DIR, f'vision_snap_{BJT_TODAY.replace("-", "")}.txt')
    if not os.path.isfile(snap):
        log(f'[X] snapshot 未生成: {snap}')
        sys.exit(1)

    log('Step 2: 采集 zthis 板块全量')
    rc = run([PY, os.path.join(SCRIPT_DIR, 'opencli_fetch.py'), 'zthis'])
    if rc != 0:
        sys.exit(rc)

    log('Step 3: 主编排 fupan_run (清残留 → 拉数据 → gen_report → verify)')
    fupan_run = os.path.join(SCRIPT_DIR, 'fupan_run.py')
    cmd = [PY, fupan_run, '--vision-snapshot', snap]
    if skip_verify:
        cmd.append('--skip-verify')
    rc = run(cmd)
    if rc != 0:
        # fupan_run 里 gen_report 的 GBK print 崩溃可能使 rc=1, 但报告已生成
        log('[!] fupan_run 非零退出 — 检查上方输出 (报告可能已生成, 末尾 GBK print 崩溃不计失败)')
        out_dir = os.path.join(DESKTOP, '股票账户监管', 'hermes每日复盘数据')
        cand = os.path.join(out_dir, f'{BJT_TODAY.replace("-", "")}_收盘复盘.md')
        if os.path.isfile(cand):
            import subprocess as sp
            chk = sp.run([PY, os.path.join(SCRIPT_DIR, 'verify_report.py')],
                         capture_output=True, text=True, encoding='utf-8', errors='replace')
            log(f'[!] 报告已存在, verify 补跑: {chk.stdout.strip().splitlines()[-2:] if chk.stdout else "?"}')
        sys.exit(rc)

    log('=== 完成 ===')
    log(f'报告: {os.path.join(DESKTOP, "股票账户监管", "hermes每日复盘数据", f"{BJT_TODAY.replace(chr(45), chr(45))}_收盘复盘.md")}')


if __name__ == '__main__':
    main()
