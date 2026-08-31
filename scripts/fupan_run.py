"""
fupan_run.py - fupan v2.9.4 orchestrator (防数据污染版)

v2.9.4 重点: 防止数据污染
  - 强制 --vision-snapshot (BJT today 必须传, 不接受 emotion_vision.json 缓存)
  - 启动时自动清空上次的残留数据 (pool list=None → list=[])
  - 每次跑都重新拉 pull_data.sh (不依赖主人提前跑)
  - emotion_vision.json 当 BJT today 一致时也删除 (不读缓存)
  - vision snapshot date 必须 = BJT today, 否则拒绝跑

Usage:
  python scripts/fupan_run.py --vision-snapshot /path/to/vision_snap_0805.txt
"""
import os, sys, subprocess, time, json, re
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\cosmo'), 'Desktop')
BJT = timezone(timedelta(hours=8))
BJT_TODAY = datetime.now(BJT).strftime('%Y-%m-%d')


def log(msg):
    print(f"[fupan_run {datetime.now(BJT).strftime('%H:%M:%S')}] {msg}")


def run(name, cmd_args, cwd=None, timeout=120):
    cwd = cwd or DESKTOP
    log(f">>> {name}")
    log(f"   $ {' '.join(cmd_args)}")
    t0 = time.time()
    try:
        r = subprocess.run(cmd_args, cwd=cwd, timeout=timeout, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')  # v2.9.6: Windows GBK 解码修复
        dt = time.time() - t0
        if r.returncode != 0:
            log(f"[X] {name} 失败 (exit={r.returncode}, {dt:.1f}s)")
            if r.stdout: print(f"  STDOUT: {r.stdout[:500]}")
            if r.stderr: print(f"  STDERR: {r.stderr[:500]}")
            return False, (r.stdout or '') + (r.stderr or '')
        log(f"[OK] {name} 完成 ({dt:.1f}s)")
        return True, r.stdout
    except subprocess.TimeoutExpired:
        log(f"[X] {name} 超时 ({timeout}s)")
        return False, "timeout"


def step0_clean_residual_data():
    log("=" * 60)
    log("Step 0: 清空上次残留数据 (防污染)")
    log("=" * 60)
    cleaned = []

    # 1. 清 pool list=None (7 个 pool 全覆盖: ztpool 也要, 0 涨停日 ztpool 也会 null)
    for f in ['ztpool', 'dtpool', 'dmpool', 'fxpool', 'czpool', 'lbpool', 'zbpool']:
        p = os.path.join(DESKTOP, f'{f}.json')
        if os.path.isfile(p):
            try:
                d = json.load(open(p, encoding='utf-8'))
                if d.get('list') is None:
                    d['list'] = []
                    json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
                    cleaned.append(f'{f}.json list=[]')
            except Exception as e:
                log(f"  skip {f}: {e}")

    # 2. 清 emotion_vision.json (不读缓存, 强制每次 vision snapshot)
    p = os.path.join(DESKTOP, 'emotion_vision.json')
    if os.path.isfile(p):
        try:
            d = json.load(open(p, encoding='utf-8'))
            old_date = d.get('date')
            os.remove(p)
            cleaned.append(f'emotion_vision.json 删除 (date=\'{old_date}\' ≠ BJT today, 不复用缓存)')
        except Exception:
            pass

    for c in cleaned:
        log(f"  [OK] {c}")

    if not cleaned:
        log("  (无残留数据)")
    return True


def step1_pull_data():
    log("=" * 60)
    log(f"Step 1: pull_data.sh · {BJT_TODAY} 最新数据")
    log("=" * 60)
    pull_script = os.path.join(SCRIPT_DIR, 'pull_data.sh')
    if sys.platform == 'win32':
        bash_cmd = subprocess.check_output(['where', 'bash'], text=True).strip().split('\n')[0]
        cmd_args = [bash_cmd, pull_script]
    else:
        cmd_args = ['bash', pull_script]
    ok, _ = run('pull_data.sh', cmd_args, timeout=150)  # 8/18: git bash curl 下载完成但进程挂起 ~6s/个, 60s 恰好超时; 150s 保险
    if not ok:
        log("[FATAL] pull_data.sh 失败")
        return False
    # v2.9.12: pull 后 pool list=None → [] (条件置空, 严禁无条件清空 — 会把有数据的 pool 删光)
    # 7 个 pool 全覆盖 (含 ztpool); 异常打印日志不静默 (8/12 曾静默失效导致 verify len(None) 崩)
    _fixed = []
    for f in ['ztpool', 'dtpool', 'dmpool', 'fxpool', 'czpool', 'lbpool', 'zbpool']:
        p = os.path.join(DESKTOP, f'{f}.json')
        if not os.path.isfile(p):
            log(f"  [WARN] {f}.json 不存在 (pull_data.sh 可能部分失败)")
            continue
        try:
            d = json.load(open(p, encoding='utf-8'))
            if d.get('list') is None:
                d['list'] = []
                json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
                _fixed.append(f'{f}.json')
        except Exception as e:
            log(f"  [WARN] {f}.json list=[] 重置失败: {e}")
    if _fixed:
        log(f"  [OK] {len(_fixed)} 个 pool list=null→[]: {', '.join(_fixed)}")
    else:
        log("  [OK] 7 个 pool 无需重置 (list 均非 null)")
    return True


def step2_gen_report(vision_snap_path):
    log("=" * 60)
    log(f"Step 2: gen_report.py --vision-snapshot {os.path.basename(vision_snap_path)}")
    log("=" * 60)
    if not os.path.isfile(vision_snap_path):
        log(f"[FATAL] vision snapshot 不存在: {vision_snap_path}")
        return False, None
    # 校验 vision snapshot 中的 date 与 BJT_TODAY
    try:
        content = open(vision_snap_path, encoding='utf-8').read()
        m = re.search(r'202\d-\d\d-\d\d', content)
        snap_date = m.group() if m else None
    except Exception:
        snap_date = None
    if snap_date and snap_date != BJT_TODAY:
        log(f"[FATAL] vision snapshot date={snap_date} != BJT today={BJT_TODAY}")
        log(f"  为防止污染 · 拒绝跑 · 请重新 snapshot {BJT_TODAY}")
        return False, None

    ok, output = run('gen_report.py',
                      [sys.executable, os.path.join(SCRIPT_DIR, 'gen_report.py'),
                       '--vision-snapshot', vision_snap_path], timeout=120)
    if not ok:
        return False, None

    # 找最新报告
    d = os.path.join(DESKTOP, r'股票账户监管', r'hermes每日复盘数据')
    if os.path.isdir(d):
        for f in os.listdir(d):
            if f.startswith(BJT_TODAY.replace("-", "")):
                return ok, os.path.join(d, f)
    return ok, None


def step3_verify(report_path):
    log("=" * 60)
    log("Step 3: verify_report.py")
    log("=" * 60)
    if not report_path or not os.path.isfile(report_path):
        log(f"[X] 报告不存在: {report_path}")
        return False
    size = os.path.getsize(report_path)
    log(f"  报告: {os.path.basename(report_path)} ({size} bytes)")
    ok, _ = run('verify_report.py', [sys.executable, os.path.join(SCRIPT_DIR, 'verify_report.py')], timeout=60)
    body = open(report_path, encoding='utf-8').read()
    if BJT_TODAY not in body:
        log(f"[X] 报告未包含 BJT today {BJT_TODAY}")
        return False
    log(f"  [OK] 报告包含 BJT today {BJT_TODAY}")
    return ok


def main():
    argv = sys.argv[1:]

    # v2.9.4: 强制 --vision-snapshot
    vision_snap = None
    for i, a in enumerate(argv):
        if a == '--vision-snapshot' and i+1 < len(argv):
            vision_snap = argv[i+1]
            break

    if not vision_snap:
        log("[FATAL] v2.9.4 强制 --vision-snapshot (防止历史缓存污染)")
        log(f"  Usage: python fupan_run.py --vision-snapshot /path/to/vision_snap_{BJT_TODAY.replace('-','')}.txt")
        sys.exit(1)

    with_dashboard = '--with-dashboard' in argv
    skip_verify = '--skip-verify' in argv
    skip_pull = '--skip-pull' in argv

    log(f"BJT today: {BJT_TODAY}")
    log(f"vision_snap: {vision_snap}")

    # Step 0: 清空残留
    step0_clean_residual_data()

    # Step 1: pull data
    if not skip_pull:
        if not step1_pull_data():
            sys.exit(1)
    else:
        log("[skip] Step 1: pull_data.sh (--skip-pull)")

    # Step 2: gen report
    ok, report_path = step2_gen_report(vision_snap)
    if not ok:
        sys.exit(1)

    # Step 3: verify
    if not skip_verify:
        step3_verify(report_path)

    log("=" * 60)
    log(f"fupan 完成 · {BJT_TODAY}")
    log(f"报告: {report_path}")
    log("=" * 60)


if __name__ == '__main__':
    main()
