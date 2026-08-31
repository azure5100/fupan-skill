---
name: fupan
description: "A股每日收盘复盘自动化工作流（短线侠数据源）— 浏览器 DOM 采集 + 脚本生成 Markdown 报告与 HTML 看板。覆盖：情绪 11 项、涨跌停统计、连扳梯队、晋级率、题材板块代表股 15 字段、板块涨跌幅、主力资金近似、跌停/炸板明细。内嵌全部数据源端点、fixture 采集规程、truth contract、9 章报告格式、网站改版应对策略与兜底经验库。适用于每日收盘后生成复盘报告、历史报告补生成、报告验证与看板生成。"
version: "2.9.5"
origin: custom
argument-hint: "复盘 / 收盘复盘 / 今日复盘 / fupan"
allowed-tools: Bash, Read, Write, Edit, WebFetch, WebSearch
metadata:
  openclaw:
    emoji: "📊"
    requires:
      paths:
        - C:\Users\cosmo\Desktop\股票账户监管\其他\fupan\scripts
        - C:\Users\cosmo\Desktop\股票账户监管\hermes每日复盘数据
---

# fupan — A股每日收盘复盘

> **数据源**：短线侠 duanxianxia.com（浏览器 DOM + HTTP 端点）· **报告存档**：`C:\Users\cosmo\Desktop\股票账户监管\hermes每日复盘数据\`
> **脚本目录**：`C:\Users\cosmo\Desktop\股票账户监管\其他\fupan\scripts\` · **经验库**：`...\fupan\references\`（历史迭代，本文件是唯一权威操作手册）

## 一、铁律（主人硬约束，违反 = 返工）

1. **数据真实性是生命线**：宁缺毋滥。绝不编造数字、绝不复用昨天的数据冒充今天、绝不静默 fallback 到旧缓存。
2. **BJT 现场计算**：`datetime.now(timezone(timedelta(hours=8)))` 算"今天"，禁止从对话历史/文件名/残留 JSON 推算日期（曾连续 3 次慢 1-2 天覆盖数据）。
3. **防数据污染**：强制 `--vision-snapshot`（拒绝则退出）；跑前清残留（6 pool `list=null→[]`、删 emotion_vision.json）；vision snapshot 日期 ≠ BJT today 拒绝运行；v2.9.5 起**解析失败 FATAL 退出**（绝不静默 fallback qxlive 旧值——8/4 缓存污染事故）。
4. **缺口如实标注**：`⚠️` 免责 + `[近似]` 派生数据 + `[待补]` 缺口，绝不静默生成"看起来真实"的数字。"假装有数据"比"说这个源不提供"更糟。
5. **DOM 是 ground truth**：目标网站每天变，以当天浏览器看到的 DOM 为准，不凭昨天/印象推算。
6. **不重新归类**：接受短线侠对板块/个股的归类结果（如锌业股份被归入"光通信"），助手不擅自改。

## 二、产出物

| 产物 | 位置 | 命名 |
|---|---|---|
| 复盘报告（md） | `C:\Users\cosmo\Desktop\股票账户监管\hermes每日复盘数据\` | `{YYYYMMDD}_收盘复盘.md` |
| 看板（html，可选） | 同上 | `{YYYYMMDD}_复盘看板.html` |
| 临时 JSON×10 | `C:\Users\cosmo\Desktop\` | `ztpool/zbpool/dtpool/lbpool/czpool/dmpool/fxpool/global/qxlive/jinji.json` |
| 板块数据 | Desktop | `zthis_sectors.json` + `zthis_sectors\sector_NN.txt` |
| 情绪快照 | Desktop | `vision_snap_{YYYY-MM-DD}.txt` |

## 三、完整工作流

### Phase A：浏览器采集（主 agent 用浏览器工具，脚本只做解析）

**A0. BJT 检查（第一步，必做）**
```bash
python -c "from datetime import datetime,timezone,timedelta; print(datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M %A'))"
```
`browser_navigate("https://duanxianxia.cn/web/main")` 看 DOM 情绪按钮是否当日值——不动 = 短线侠未刷新（周末/节假日为最近交易日快照，正常，报告如实标注）。

**A0.5. opencli 浏览器通道（v2.9.5 已验证 · browser MCP 不可用时的替代）**

opencli（`@jackwener/opencli`，npm 全局）的 Chrome 扩展 + daemon(`127.0.0.1:19825`) 提供真实浏览器 DOM 通道。**自动合成层对 SPA 全失败**（`probe`/`generate`/`cascade`/`record` 均拿不到数据，勿浪费时间）——直接用底层 daemon API：

```bash
# 0. 桥接检查
opencli doctor   # 必须 [OK] Daemon + [OK] Extension connected

# 1. 导航 → 返回 tabId（后续所有 exec 必须带）
curl -s -X POST http://127.0.0.1:19825/command -H "Content-Type: application/json" -H "X-OpenCLI: 1" \
  -d '{"id":"nav1","action":"navigate","url":"https://duanxianxia.cn/web/main","workspace":"default"}'

# 2. exec 任意 JS（data 可能是 JSON 字符串，先 JSON.parse）
curl -s -X POST http://127.0.0.1:19825/command -H "Content-Type: application/json" -H "X-OpenCLI: 1" \
  -d '{"id":"exec1","action":"exec","code":"<js>","workspace":"default","tabId":<TAB_ID>}'
```

- **`/web/main` 情绪 11 项在 `#qxiframe`**（同源，contentDocument 可读）：`document.getElementById('qxiframe').contentDocument.querySelectorAll('button')` 过滤 `label：值` 文本 → 存 `vision_snap_{YYYY-MM-DD}.txt`（必须 `button "label：值"` 每行格式，parse 正则要求）
- **转义铁律**：exec code 里的字符串换行必须双反斜杠——git bash heredoc 会把 `\\n` 折叠成 `\n` 造成裸换行 SyntaxError。**用 Write 工具写 node 脚本再 `node script.js`**（JSON.stringify 自动处理转义），禁止 heredoc 内嵌大段 JS
- 2026-08-05 实测：qxlive iframe DOM = 当日真实值（95/103/+505/3725/70.6%），而 qxlive.json 端点 = 8/4 缓存（92/585/3642）——**DOM=ground truth 再验证**；opencli 通道与 browser MCP 等效
- **已固化采集脚本**：`scripts\opencli_fetch.py`（python 调 daemon，无需 curl/node）——`python opencli_fetch.py vision`（→ scripts\vision_snap_{YYYYMMDD}.txt）、`python opencli_fetch.py zthis`（→ Desktop\zthis_sectors.json 全量）、`check`（桥接自检）。**前置**：Chrome 需打开且扩展已连接（`opencli doctor` 验证）；Chrome 关闭时用 `chrome.exe --load-extension="C:\Users\cosmo\.npm-global\node_modules\@jackwener\opencli\extension"` 拉起

**A1. 情绪快照（11 项）— `/web/main`**
- 方式①（browser MCP）：`browser_snapshot()` 一次拿 11 个 `button "情绪指标：50"` 格式按钮（QX/ZT/DT/KQXY/HSLN/LBGD/SZ/XD/PB/ZTBX/LBBX）
- 方式②（opencli）：读 `#qxiframe` 的 button 文本（见 A0.5）
- 主 agent 原样存为 `vision_snap_{YYYY-MM-DD}.txt`（Desktop），**必须是完整 DOM 格式**，禁止精简成 `1. 情绪指标：50`（parse 正则要求 `button\s+"label：value"`）
- HSLN 去掉"亿"单位（`-790` 而非 `-790亿`，否则 float() 崩溃）
- ⚠️ 必须对 `/web/main` 跑 snapshot；对 `/web/zthis` 跑会 parse 0 项静默失败
- **v2.9.5 硬防护**：gen_report.py 传了 `--vision-snapshot` 但解析失败 → FATAL 退出，绝不静默 fallback qxlive 旧值

**A2. 板块采集 — `/web/zthis`（v2.9.5 全量采集，突破原 9 row 截断）**
- **优先 opencli 全量采集**（一条 JS 拿全 15 板块 + 全部股票，2026-08-05 实测 103 股无截断）：
  1. `document.getElementById('showhide')` 点"全部展开"——**必须 button 本体**（`<button id="showhide">`），点外层 div 无效；click 后 DOM 立即渲染（body 文本 301 → 10821 字符）
  2. 结构：`#ztlist > .ztitem`（板块标题：`名称（pct%）`+涨停数）紧邻兄弟 `.zt > table.ztlist`（15 列）
  3. 单段 JS 遍历 `.ztitem`↔`.zt` 配对 → 直接写 `C:\Users\cosmo\Desktop\zthis_sectors.json`（`{date, sectors:[{name,pct,zt_count,stocks:[{name,code,pct_chg,pre_close,ban,lianban,board_type,first_limit,last_limit,amount,free_cap,total_cap,turnover,reason,dragon_tiger}]}]}`）
- 方式②（browser MCP 受限时 fallback，**9 row 截断限制仍在**）：
  - 折叠态 snapshot → 板块数 = `element_count - 8`（历史: 22→14、18→10、17→9；9~14 个）
  - **单板块逐个展开**（禁止"全部展开"：1359 元素被 ~50KB/1322 行 buffer 截断）
  - 每板块流程（循环 N 次，N=当天板块数，**绝不硬编码数量**）：
    1. `browser_navigate(/web/zthis)` — **必须重开**！click 后 DOM 重渲染 ref 失效，不重开报 "Unknown ref"
    2. `browser_click(ref=e{8+n})`（板块 ref 从 e8 起，编号必须按 DOM 顺序，不按 vision 顺序）
    3. `browser_snapshot()` → ~134 元素单板块展开
    4. 主 agent 把 snapshot 文本写入 `C:\Users\cosmo\Desktop\zthis_sectors\sector_{NN:02d}.txt`（编号 = DOM e8..eN 顺序）
  - **fixture 必须是真实 DOM 文本**（禁止 stub/placeholder）；15 列同全量结构
  - 写盘方式：≤5KB 用 `templates\fixture-writer-template.py`（1.5min/板块）；≥5KB 走 patch append（每段 ≤3KB，patch `mode='replace'` 必须带顶层 path 参数）
  - **9 行限制**：browser_snapshot 对长 DOM 主动截断（固定 9 row），≥10 涨停板块 fixture 会不完整——接受"能采多少采多少"（≥1 row 进 json；0 row 保留板块名+pct+zt_count、stocks=[]），禁止中途放弃或 merge 半成品
  - 板块 fixture 合并：`merge_fixtures.py`（strict→fuzzy 匹配恢复 OCR 错字 → 差集交互确认 → 写 `captured_at/fixture_count/vision_count`）

**A3. 板块涨幅 pct（可选）**：vision 折叠态抓 `/web/zthis` 板块名+涨幅%（数字准、文字会错位——代表股必须用 DOM fixture）；8/4 起 vision 文本可能无涨停数，从 fixture 板块头补

### Phase B：脚本执行（cwd 必须在 Desktop！）

```bash
cd /c/Users/cosmo/Desktop

# B0. 一键流程（v2.9.6 首选：桥接自检→自动拉起 Chrome→vision 采集→zthis 全量→主编排→verify）
python "C:\Users\cosmo\Desktop\股票账户监管\其他\fupan\scripts\fupan_oneclick.py"
#     补生成历史报告: python fupan_oneclick.py --date 2026-08-05   (跳过采集, 用已有 snapshot)
#     调试: --skip-verify
#     产出: {date}_收盘复盘.md (报告)。看板独立: 调 review-dashboard skill 手工渲染 (v2.9.9 起不自动串联)

# B1. 拉数据（必须从 terminal 跑，fupan_run.py 内调会 WinError 2）
bash "C:\Users\cosmo\Desktop\股票账户监管\其他\fupan\scripts\pull_data.sh"

# B2. 主编排（Step0 清残留 → Step1 强制重拉 → Step2 校验 snapshot 日期 → gen_report → Step3 verify）
python "C:\Users\cosmo\Desktop\股票账户监管\其他\fupan\scripts\fupan_run.py" --vision-snapshot "C:\Users\cosmo\Desktop\vision_snap_{YYYY-MM-DD}.txt"

# B2b. 补生成历史报告（v2.9.6 新增 --date；次日凌晨补昨日报告时必用，否则按 BJT today 生成错配脏数据）
python scripts\gen_report.py --date 2026-08-05 --vision-snapshot "...\vision_snap_20260805.txt"

# B3.（可选）HTML 看板（fupan_run 的 --with-dashboard 是死参数，须手动跑）
python "C:\Users\cosmo\Desktop\股票账户监管\其他\fupan\scripts\build_dashboard_v2.py" "C:\Users\cosmo\Desktop\股票账户监管\hermes每日复盘数据\{YYYYMMDD}_收盘复盘.md"
```

- **顺序铁律**：gen_report → build_dashboard → verify。verify 末尾清理 10 个临时 JSON，若先跑则看板静默产出空数据
- **成功诊断捷径**：报告 mtime 不变 = gen_report.py 末尾写盘段缺失，`tail -20 gen_report.py` 检查（曾经 838 行被截成 545 行还 exit 0）
- **跑前检查**：`zthis_sectors.json` 是否含 `_partial: true`（有 = fixture 截断，报告应 WARN 标注）

### Phase C：验证与归档

1. `verify_report.py` 无参数自动跑（35 项：章节齐全、动态数据点比对、mermaid、防泄漏；期望值 vision-first（emotion_vision.json）→ pool 兜底；末尾自动清理临时 JSON）
2. 人工抽查：报告 §2.1 情绪 11 项与 vision_snap 一致；§4.2 代表股子表存在；mtime 新鲜
3. 看板检查：>40KB、摘要无 0 项、红涨绿跌（不信 vision 自检，自己读 CSS）、折叠交互正常

## 四、数据源与端点

### 4.1 HTTP 端点（`https://www.duanxianxia.com`，UA=Mozilla/5.0）

| 端点 | 落盘 | 关键结构 |
|---|---|---|
| `/vendor/stockdata/global.json` | global.json | `data.diff[]`: f12 代码/f14 名称/f2 收盘/f3 涨跌幅/f4 涨跌；20 项全球指数 |
| `/vendor/stockdata/jinjidata.json` | jinji.json | `html` 含 `<tr><td>路径</td><td>统计</td>`，regex 提取 |
| `/api/getLastQxlive` | qxlive.json | `qxlast` 13 通道时间序列，**末值=当前**；周末/节假日返回旧缓存 |
| `/data/getZtPoolData/` 等 7 个 | ztpool~fxpool.json | `list:[r...]`: r[2]涨幅% r[4]炸板次数 r[6]概念(`+`分隔) r[7]板数 r[8]成交额；**0 涨停日可能 `list:null`** |

### 4.2 被封锁端点（不要用）
`x.duanxianxia.cn/web/amount`(403) · `bm.duanxianxia.com/api/getWebKaipanPlate`(403) · `x.duanxianxia.cn/data/getZtPoolData/`(404) · `/api/getHisZtPool` POST(0 bytes) · 东财 push2(非 CN IP GeoBlock)

### 4.3 网站改版应对（目标网站变化策略）

**症状识别**：① pull_data.sh 产出空 JSON + verify 全 fail → **站点改版**；② 报告板块数 ≠ 当前 DOM clickable 数；③ vision 文本格式变化；④ merge 报 fixture-vs-vision 差集。

**应对流程**：
1. 浏览器打开 `https://www.duanxianxia.com/web/<page>.html`（如 pool.html/global.html），读 `<script src="/static/js/base.js">` 前的**未混淆内联 script**，`$.ajax({url:...})` 是明文端点（无浏览器工具时用 opencli exec 读 `document.querySelectorAll('script:not([src])')` 文本，等效）
2. base_url 由 base.js 读 `/vendor/stockdata/datasource.json` 运行时决定
3. 发现新端点 → 更新 `pull_data.sh` 的 URL + 本文件端点表 → 验证 → 完成 skill 版本更新（version bump + changelog）
4. 无法确认时**暂停并告知主人**，绝不脑补

**truth contract（真值契约）**：短线侠当前 DOM 状态 = ground truth；旧 fixture 残留是"错的判断"不是"错的事实"——改的是判断（重采），不是数据。同类：vision date 权威、zthis_sectors.json 优先于 Counter、qxlive 端点可能缓存昨天。

### 4.4 数据优先级

```
情绪字段:  DOM snapshot(vision_snap, 主人看到的页面) > 主人录入(emotion_overrides.json) > qxlive+pool 交叉验证
板块字段:  DOM fixture(代表股/涨停数, 字符精准) > /web/main regex(板块+涨停数) > vision(pct%, 数字准文字错) > Counter 反推(仅 §5.2/§6.2 跌停路径 + fallback, 标[近似])
```

- qxlive 交叉验证：ZT=`len(ztpool)`、DT=`len(dtpool)`、LBGD=`max(连板数)`、PB=`zt/(zt+zb)`；其余 7 项 qxlive 独占
- **任何位置读情绪字段必须走三路 helper**（vision → overrides → endpoint），禁止单点直读 endpoint（50% fix 陷阱）
- §5.2/§6.2（跌停/跌幅）**永远**用跌停池 r[6] Counter 反推，绝不用 zthis 数据（语义矛盾）

## 五、报告格式规范（9 章 + 2 附录）

```
# A股市场复盘报告 · YYYY年MM月DD日（周X）
## 一、市场概览       1.1 A股7指数 / 1.2 全球20指数对比
## 二、市场情绪       2.1 情绪面板11项+数据源追溯表 / 2.2 涨跌停统计 / 2.3 连扳梯队 / 2.4 晋级率 / 2.5 综合判断
## 三、涨幅排行榜     3.1 当日涨幅TOP15 / 3.2 成交额TOP10
## 四、市场题材全景图 4.1 涨停题材热度TOP13 / 4.2 板块代表股15字段子表(每板块h4+表, 0row也渲染表头+WARN, v2.9.5全量采集无截断) / 4.3 mermaid主线结构图
## 五、板块涨跌幅TOP10  5.1 涨幅(按涨停数) / 5.2 跌幅(按跌停数, Counter路径)
## 六、主力资金候选   6.1 净流入TOP10 [近似]
## 七、…(cross-ref) / 附录A 跌停明细 / 附录B 炸板TOP
## 复盘总结 (mermaid xychart)
```

- **数据源追溯表**：§2.1 末尾必须列每个字段的来源（DOM snapshot 真实值 / pool 实时 / qxlive），fallback 字段标 ⚠️
- **gap markers（v2.9.12 起按生成器实际输出校准；8/11 及以后验收报告同款）**：
  - Gap1 §1.1: `> ⚠️ 短线侠数据源未包含**科创板 000688** 与**北证 50** 指数。`（verify 检查"标注科创板缺失"）
  - Gap2 §3.2: 标题为 `### 3.2 成交额 TOP10（涨停池内）`（5日/10日/20日排行不生成；verify 检查 "[v2.2.0] §3.2 成交额 TOP10 标题"）
  - Gap3 §6: `> 数据源：涨停池题材反推（无板块级资金接口）。` + `### 6.1 净流入候选 TOP10（涨停驱动）` 表列 `推断`（近似语义，verify 检查"标注主力资金数据源"）
- 涨停梯队/晋级率/涨跌停统计 2.2 的 9 项（涨停/连扳/炸板/跌停/冲涨/大面/热门/封板率/炸板率）来自 pool 实时
- 连扳梯队：lbpool 空时用 vision LBGD + ztpool r[7] 反推；**禁止显示"无连扳股"**
- 周末/节假日：报告 header 日期 = 短线侠数据日（最近交易日），banner 注明"数据截至 X（周末短线侠不刷新）"

### HTML 看板 4 条硬约束（主人不许妥协）
1. **红涨绿跌**（`--red-up:#ef232a` / `--green-down:#14b143`）；vision 自检在 dark theme 下按国际习惯会看反——不信 vision，读 CSS
2. **折叠布局**：数据多板块用 `<details class="foldable">`；仅 §3.1 TOP15 和 §8.1 成交额默认 open
3. **左侧浮动目录**：`.toc{position:sticky;top:20px;max-height:calc(100vh-40px);overflow-y:auto}`；TOC 匹配 md 9 章结构
4. **注明数据来源与日期**：顶部 banner 必含复盘日期/生成时间/数据源标签+链接

模板：`scripts/dashboard_template_master.html`（50KB，主人审美基准）——**cp 模板 verbatim → 注入数据**，禁止重做 CSS/改颜色/加功能。构建脚本 `build_dashboard_v2.py`：subsection 匹配按"最具体子串先匹配"；输出摘要出现"0 项"= 匹配错位。

## 六、兜底经验库（已踩坑验证，按主题）

### 6.1 Fixture 写入
- 写盘演进史：write_file 8KB+ 截断(50-70%失败) → execute_code(**已废弃**,被系统BLOCKED) → patch append(每段≤3KB) → **fixture-writer-template 单脚本**(<5KB 适用, 1.5min/板块)
- 写盘后立即验证行数：`len(open(fixture).readlines())` ≈ 涨停数×12（33 涨停 → ~400 行）；< 阈值 = 截断必须重写
- 大板块预警：单板块 ≥30 涨停或 element_count ≥500 → 主动验证；板块 ≥10 或总涨停 ≥100 → **跑前给主人 A/B/C 选项**（A 全采 10-15min / B 跳过留"—" / C 仅 2-3 最大板块）
- Windows 路径必须 r-string 防 `\u` 转义；patch 顶层 path 参数必带
- **禁止用 delegate_task 写 fixture**（主人明令：大模型不崩，自己跑）

### 6.2 数据提取
- vision snapshot 必须完整 DOM 格式；parse 失败（<11 项）**报错不静默**（fallback = 跨日错配）
- vision 板块数/排序 ≠ DOM（vision 抓全页面含隐藏内容）；fixture 按 DOM clickable 顺序（e8..eN）
- 板块名 OCR 错字：fuzzy-match（SequenceMatcher ratio ≥0.7）1:1 单字差自动恢复
- merge 时 **fixture 板块名是 ground truth**，vision 只提供 pct
- fetch_zthis_v2 regex 必须容忍 2-4 空格缩进（真实 snapshot 是 2 空格）
- 15 字段 dict key：`pct_chg/ban/lianban/free_cap/total_cap`（易错写全拼）；stocks 保留 list of dict 不 join 字符串

### 6.3 日期与行情时段
- **qxlive 跨日缓存**：16:30 后拉可能仍是前一天值；用 pool 交叉检查，**不掩盖，报告中并列展示**
- 0 涨停日修复 6 pool `list=null→[]`（pull_data.sh 已覆盖）
- 周末/节假日短线侠 T+1 凌晨刷 = 周五快照（正常不是 bug）
- 行情级别与板块数**无固定关系**（7/22 震荡=7、7/23 大涨=11、7/24 大跌=9），每天实测
- 被系统阻断时问主人确认 BJT，不自己脑补

### 6.4 工具 blocker fallback 链
```
execute_code 卡 → patch append；terminal 卡 → write_file+read_file；
patch 报 path required → path 放顶层参数；write_file 8KB+ 截断 → 分批(1.5KB+3KB×3)；
browser 工具卡/缺失 → opencli daemon（A0.5，navigate+exec 等效 browser_navigate/snapshot）；
全卡 → 告知主人 + 暂停等批准
```
- patch 任何文件前必须完整 read_file（不带 offset/limit），否则可能截断文件
- system 可能自动 rebuild gen_report.py（v2.9.0 事故：545→351 行清空全部历史 fix）——**每次跑前 diff 头部+末尾**

### 6.5 验证
- **验证器查结构不查内容**：章节头齐全、行数范围、mermaid 渲染、gap 标记、文件大小、无源码泄漏、mtime 1 小时内；具体数值必须从 JSON 运行时推导期望值（硬编码期望 = 第 2 天全假失败）
- fixture 完整性：行数 ≈ 涨停数×12；element_count ≈ 涨停数×18；parse 后 `len(stocks)==zt_count`
- 每次大改后写 `hermes-verify-<topic>.py` 到 Temp，跑完即删

### 6.6 清理协议（流程边界清理）
- pull_data.sh 开头清（防御）→ gen_report 中间**不清** → verify 末尾清
- 清 10 个临时 JSON；**必须保留**：emotion_vision.json、zthis_sectors.json、emotion_overrides.json
- 失败时不清（保留供 debug）；禁止"生成器里写 cleanup"；禁止"失败也清理"
- clean-slate 协议（目录级）：`rm -rf ~/Desktop/zthis_sectors && mkdir -p ~/Desktop/zthis_sectors`（单文件通配符方案已废弃——跨平台会误删整个目录）

### 6.7 已废弃方案（不要再走）
① v2.8.9 "row 数≠zt_count 拒绝 merge" → 改为 WARN+接受（0 row 板块消失比截断更糟）② execute_code 写盘 ③ 单文件 rm clean-slate ④ "vision 板块数必须=DOM"（天然不一致，以 DOM 为准）⑤ §4.1 Counter 反推主路径（v2.9.2 永久改用 zthis_sectors.json）

## 七、故障排查速查表

| 症状 | 原因 | 处理 |
|---|---|---|
| 报告 mtime 不变 | gen_report.py 写盘段缺失 | `tail -20 gen_report.py`，补 `with open(out_path,'w')` |
| verify 全 fail + 空 JSON | **站点改版** | 浏览器看 /web/main 找新端点（§4.3） |
| §2.1 情绪错（旧值 92/102/+585） | 缓存污染 | 强制重跑 --vision-snapshot；Step0 清残留；v2.9.5 起解析失败直接 FATAL |
| `AttributeError: 'str' object has no attribute 'get'` | gen_report L628 fallback 产出字符串列表 | 改为 dict 列表 `[{'name':n,'zt_count':cnt}]` |
| vision snapshot IGNORE | 对 /web/zthis 跑了 snapshot（缺 11 button） | 改对 /web/main 跑 |
| lbpool 为空显示"无连扳" | fallback 缺失 | vision LBGD + ztpool r[7] 正则 `(\d+)连板` 反推 |
| parse_snapshot 返回 None | DOM 文本变了 | 更新 fetch_vision.py KEY_MAP；类型错改 parse_value |
| patch 报 path required | patch 缺顶层 path | path 放顶层参数 |
| qxlive 数据像昨天 | 跨日缓存（Pitfall #15） | pool 交叉验证 + 报告并列展示，不掩盖 |
| opencli exec 报 SyntaxError | heredoc 转义折叠 | 用 Write 写 node 脚本再 `node script.js`（禁止 heredoc 内嵌大段 JS） |
| opencli 无 browser 窗口/扩展掉线 | daemon 或扩展未连 | `opencli doctor` 诊断；重开 Chrome + 扩展 |
| 报告 mtime 新但 §2.1 旧值 | 复制/生成时序 | 跑完**立即**读源文件验证（gen_report 输出"解析 N 项"≠报告已含新值）；以 hermes 目录源文件为准复制 |
| 报告 §4 全空（看板 0 题材卡） | Desktop\zthis_sectors.json 消失 | 重采 `opencli_fetch.py zthis` 再跑；v2.9.8 起 opencli_fetch 双份写（Desktop + scripts 缓存），gen_report 双路径读（Desktop 优先 → scripts 兜底） |
| §4 板块分类与页面不符（8/10、8/13 事故） | **短线侠收盘后对板块重新分类**（8/10：18:11 采集 16 板块 → 19:06 变 14 板块；**8/13：18:13 采集 11 板块 → 18:38 变 8 板块**，59 股总数不变） | 用户反馈 §4 与页面不一致时：重采 `opencli_fetch.py zthis`（DOM ground truth）→ 重生成（fupan_run --vision-snapshot，无需重采 snapshot）→ verify。**经验：收盘后板块分类可能延迟稳定（8/10、8/13 两次复现，窗口 18:00-19:00），报告生成后若页面再变需重采；8/13 实测 11 板块→8 板块（医药 14/算力·半导体 14/其他 9/大消费 8/电力 6/公告 3/机器人 3/业绩线 2）** |
| 报告缺 §4.1.1 子表 | 生成器章节丢失 | 以 8/4 合格报告为格式基准补全 |
| gen_report.py 被自动 rebuild | system 行为 | 跑前 diff 头部/末尾，重新应用历史 fix |
| verify 后报告 §2.1 变旧值（95/505 混入） | **verify 自己 import gen_report 的副作用**：`from gen_report import _emotion_fallbacks` 执行顶层代码，无 snapshot 参数 → qxlive fallback 重生成并覆盖正确报告 | 识别：报告 mtime 晚于 gen_report 完成 ~1.8s；已修（v2.9.7：verify 改读 emotion_vision.json 判断；gen_report 加无 snapshot 总闸 FATAL） |
| gen_report 报 `float('-383亿')` ValueError | opencli_fetch HSLN 未去"亿"单位 | 已修（v2.9.7 opencli_fetch vision 采集时剥亿）；snapshot 里 HSLN 必须是纯数字 |
| verify 期望 `76.0`/`-383.0` 匹配不上 | float str() 尾缀（str(76.0)='76.0' ≠ 报告 **76**） | 已修（v2.9.7 verify 期望值 `{:g}` 格式化） |
| 一键脚本冷启动失败（daemon 未运行） | ensure_bridge 只查扩展，daemon 死了直接拉 Chrome 没用 | 已修（v2.9.7 两阶段：daemon 未响应 → `opencli doctor` lazy 启动 → 再拉 Chrome） |
| verify 报 `len(dt)` NoneType 崩溃 | **0 跌停/0 涨停日站点 pool `list:null`**（非 []，8/12 dtpool 实测）| 已修（v2.9.12）：verify `_load` null→[] 防御 + `'X' in _eo_data` 存在性判断（**0 值也是有效数据**，`.get()` truthiness 会把 0.0 判为缺失）；fupan_run step1 条件置空（**严禁无条件 `d['list']=[]`** — 会把有数据的 pool 删光，8/12 发现该静默污染 bug）|
| §2.3 连板梯队缺最高板 / §2.5 连扳高度偏小 | **lbpool 最高板行 r[7] 裸 `'连板'`**（无数字前缀，8/12 百花医药 7天7板 首次实测；旧行如 `'2连板'` 带数字）| 已修（v2.9.12）：gen_report `_ban_count_of` 裸行 → ztpool 同代码补板数（`X天Y板`）→ fallback vision LBGD；verify 最高板检查同步容错（裸行板数用 LBGD）|
| 报告 §5.2 出现两次 / mermaid 后孤立 ``` / xychart 首尾缺引号 | **gen_report 历史残留 bug**（8/11 起每份报告都有，verify 查结构不查内容漏网）| 已修（v2.9.13）：删重复 §5.2 块 + 删多余 ``` + xychart `["{names}"]` 补引号。**人工抽查必扫三处**（重复标题、fence 数量、x-axis/bar 引号）|

## 八、文件清单

**现行脚本**（`...\fupan\scripts\`）：`fupan_oneclick.py`(一键流程 v2.9.7, 首选入口: 两阶段桥接拉起 daemon+Chrome; v2.9.9 起不含看板步骤) · `fupan_run.py`(主编排 v2.9.6: run() UTF-8 解码) · `gen_report.py`(报告生成 v2.9.8: --date 补生成 + 写 emotion_vision.json + FATAL 硬防护(含无 snapshot 总闸) + stdout UTF-8 + §4 排版 + zthis 双路径读) · `verify_report.py`(验证+清理 v2.9.7: 期望值 vision-first + `{:g}` 格式化 + **不再 import gen_report**) · `pull_data.sh`(拉数据) · `opencli_fetch.py`(opencli 采集 v2.9.8: vision/zthis 双模式, HSLN 去亿, zthis 双份写) · `fetch_zthis_v2.py`(fixture 解析) · `fetch_zthis.py`(vision 解析) · `merge_fixtures.py`(fixture-vision 合并) · `collect_fixtures.py`/`collect_fixture_smart.py`(采集辅助) · `fetch_vision.py`(情绪 parse) · `build_dashboard_v2.py`(旧看板)

**数据契约（v2.9.5 闭合）**：fupan_run Step0 删 emotion_vision.json → gen_report 解析 snapshot 后写入（11 项）→ verify 从它读期望值（vision-first → pool 兜底）。三个环节缺一即断链：verify 会拿 qxlive 旧值当期望（92/585 误报事故）。

**模板**：`templates\fixture-writer-template.py`（15 元组 ROWS + write_fixture 固定 DOM 结构）· `templates\zthis_sectors.json`（格式基准）· `scripts\dashboard_template_master.html`

**淘汰清单**（冗余，可归档/删除）：`merge_fixture_v276.py`（被 merge_fixtures 取代）· `build_dashboard.py` + `dashboard_template.html`（v1 废弃）· `dashboard_v2_template.html`、`dashboard_template_claude.html`（无引用）· `verify_v291.py`、`hermes_adhoc_verify.py`（8/5 一次性硬编码验证，日更必 fail）

## 九、完成标准（全部勾选才算完成）

- [ ] 报告含 BJT today 日期，mtime 新鲜
- [ ] §2.1 情绪 11 项与 vision_snap 一致（无旧数据残留）
- [ ] §4.2 板块代表股子表齐全（0 row 板块也有表头+WARN）
- [ ] gap markers 三处标准文案在
- [ ] verify_report.py 通过（或已人工确认偏差原因）
- [ ] 10 个临时 JSON 已清理，Desktop 干净
- [ ] 看板（如生成）>40KB 且摘要无 0 项
- [ ] 站点结构/流程有变化 → 本 skill 已同步更新（version bump + changelog）

---

## 十、变更日志（changelog）

- **v2.9.16（2026-08-28）**：**§4.1 板块重分类第四次复现（16→14，细分→产业链合并口径）**——17:37 采集 16 细分板块（公告 18/农林牧渔 11/AI应用 9/大消费 6/化工 6/医疗医药 4/AI硬件 4/机器人 4/PCB 3/算力 3/地产基建 3/贵金属 2/消费电子 2/半导体 2/光通信 1/其他 4 = 82）生成报告 → 17:38 探测页面 16 板块一致（当时误判无重分类！）→ 20:06 用户反馈 §4 与源数据不符 → 探测确认页面已变 **14 合并板块**（大农业 12/算力·半导体产业链 11/化工 11/AI应用 7/电力 6/医药 5/大消费 5/其他概念 5/PCB产业链 4/业绩增长 4/机器人 4/网络安全 3/地产产业链 3/黄金珠宝 2 = 82 股，总数不变）。**教训**：17:37 采集后 38 分钟探测一致**不保证**后面不变——8/10/8/13/8/17 同款事故第四次复现，合并动作发生在采集后 1-2.5 小时内（17:37 → 20:06 已变）。处理：重采 zthis（14 板块 82 股）→ gen_report 重生成 → verify 0 失败 → 4.1 与页面 ground truth 完全一致。**铁律更新**：fupan 生成后**如用户反馈 §4 不符，无论生成后探测多少次一致，都要重采核对**；收盘后 17:30-20:30 采集的 zthis 分组都可能被站点后续合并
- **v2.9.15（2026-08-21）**：**站点 zthis 板块名服务端渲染故障（ztname 空）+ 概念语义归并兜底**——18:12 采集 zthis 只有 1 个无名板块（54 涨停 / +11.31%），板块名 `.ztname` span 内容为空。**排查链**：①30s 多时间点观察 .ztname 始终为空（非延迟加载）②页面只调 `zthis.js` + `POST /api/getHisZtPool`（板块 HTML 服务端渲染，无独立板块 API；API 需 cookie 无法直连）③表格 15 列无板块/概念字段 ④站点对所有人故障（非采集问题）。**兜底方案**（不修解析逻辑，修数据）：页面 DOM 15 字段个股数据完整 → ztpool 概念标签（索引 6，`+` 分隔）→ **语义归并表** `SECTOR_MAP`（算力/半导体产业链：CPO/光网络/液冷/AI算力/PCB/半导体/存储/光刻/封装…；医药：创新药/中药/合成生物/AI医疗/mRNA/疫苗…；机器人：机器人/人形/减速器/AI验布机…；贵金属：黄金/白银/珠宝；业绩增长：半年报增长/中报扭亏/回购/定增/央企…）→ 重建 zthis_sectors.json（格式兼容）→ gen_report 重生成 → verify 0 失败。结果：6 板块 54 股（算力 24 / 医药 8 / 机器人 8 / 业绩增长 7 / 贵金属 4 / 其他 3），4.1 数据源标注"概念标签反推兜底"。**经验**：①先试"第一概念分组"太散（49 组）→ 高频概念归属法仍散（36 组）→ **语义归并表**才可用（6 组）；②板块名空 ≠ 板块结构坏，个股 15 字段 DOM 始终完整，可复用；③ztpool 概念标签是细粒度（153 个/54 股），**不能**直接当板块。**后续（用户反馈"源数据有10个板块"）**：站点约 30-60 分钟后恢复板块名（10 板块 54 股：光通信 9/医药 8/算力·半导体 8/有色 7/机器人 5…）→ 重采 zthis → gen_report 重生成 → verify 0 失败，4.1 与页面 ground truth 完全一致。**最终结论**：站点板块名故障是**临时性**的（约 1 小时内自愈）——用户反馈数据不符时**先重采**（可能已恢复），语义归并兜底仅作应急；若重采仍 1 板块，再走兜底并告知用户站点故障中
- **v2.9.14（2026-08-17）**：**§4.1 板块重分类三次复现（16→13，细分→产业链合并口径）**——17:56 采集 16 细分板块（半导体 11/AI散热 5/算力 5/PCB 9/被动元器件 2/电力 4/AI配电 6/农林牧渔 6/公告 6…）生成报告 → 用户反馈 §4.1 与实际不符 → 探测确认页面实际 **13 合并板块**（算力/半导体产业链 21 / 化工 11 / PCB产业链 10 / 光通信 9 / 大消费 9 / 电力/数据中心供电 9 / 机器人 8 / 医药 8 / 其他概念 6 / 有色金属/小金属 5 / 大农业 4 / AI应用 3 / 军工/航天 3 = 106 股）。**验证要点**：①总涨停数一致（106），仅分组口径变化；②`#showhide` 展开/收起**不影响**分组（点击前后均 13 板块，非视图切换）；③与 8/10（16→14）、8/13（11→8）同款事故**第三次复现**——确认"收盘后板块分类延迟稳定"为常态（17:56 采集时仍是旧分组）。处理：重采 zthis（13 板块 106 股）→ gen_report 重生成 → verify 35/35 通过。**经验**：收盘后 17:30-18:30 区间采集的 zthis 分组不可信，用户反馈 §4.1 不符时优先重采重生成而非修解析逻辑
- **v2.9.13（2026-08-13）**：**3 个历史遗留格式 bug 修复**（8/11 起每份报告都带，verify 不查所以漏网，8/13 人工抽查首次发现）：
  - **§5.2 重复输出**：gen_report 有两个完整相同的 `### 5.2 跌幅 TOP10（按跌停数反推）` 输出块（历史编辑残留，表头一"板块"一"题材"）——8/11/8/12/8/13 四天报告都输出两个 §5.2。修复：删除后块保留前块（"板块"表头）；无跌停日显示"今日无跌停票"（原两行）
  - **4.3 mermaid 后多余孤立 ```**：L429 历史残留多 append 一次 ```，markdown 把后续内容渲染成代码块。修复：删除，fence 3→2（mermaid 开/闭各 1）
  - **xychart 引号缺失**：`x-axis [{names}]` 用 `'", "'.join()` 拼串但首尾元素没包引号 → `[大唐发电", ..., 华电能源]` 首尾缺 `"`，mermaid 渲染失败（8/11/8/12 同款）。修复：`x-axis ["{names}"]` / `bar ["{vals}"]`
  - **经验**：verify 查结构不查内容（§5.2 重复、孤立 fence、mermaid 引号都查不到）——**人工抽查必须扫这三处**；8/13 报告修复后 26286 bytes，35 项 verify 通过
  - **§4.1 板块重归类二次复现（同日）**：18:13 采集 11 板块生成报告 → 用户反馈页面实际 8 板块 59 涨停 → 18:38 重采（DOM ground truth）确认 8 板块（医药 14/算力·半导体产业链 14/其他 9/大消费 8/电力 6/公告 3/机器人 3/业绩线 2 = 59 股）→ fupan_run 重生成 → verify 通过。与 8/10 事故同款，确认"收盘后板块分类延迟稳定"非偶发，入故障排查表
- **v2.9.12（2026-08-12）**：**0 跌停日 verify 崩溃 + lbpool 最高板裸行** 双修复（8/12 首次跑 35/35 通过）：
  - **verify `len(dt)` NoneType 崩**：0 跌停日 dtpool.json `list:null`（站点 0 家时返回 null 而非 []）。修复：①verify `_load()` null→[] 防御；②`_zt_exp/_dt_exp/_fb_exp` 改用 `'X' in dict` 存在性判断（`.get()` 对 0.0 是 falsy，跌停 0 天必走 pool 路径崩）；③连扳高度期望 vision LBGD 优先（pool 反推在最高板裸行时偏小）
  - **fupan_run step1 无条件清空 bug**：`d['list'] = []` 无条件把 6 个 pool（含 zbpool/lbpool 等有数据池）清空，仅 ztpool 幸免——改为 `list is None` 条件置空 + 7 pool 全覆盖（含 ztpool）+ 异常打日志不静默。**疑点未解**：8/12 该循环实际未生效（zbpool 有数据可证，手动重现同款代码成功），已加诊断日志，下次跑观察
  - **lbpool 最高板行 r[7] 裸 `'连板'`**（无数字前缀，8/12 百花医药 7天7板 首次）：gen_report `(\d+)连板` 匹配失败 → 最高板被跳过 → §2.3 梯队缺 7 板、§2.5 连扳高度错显示 4 板（数据缺陷）。修复：gen_report `_ban_count_of()` 裸行 → ztpool 同代码补（`X天Y板`/`X连板`）→ fallback vision LBGD；verify 最高板检查同款容错。8/12 报告重生成后 §2.3 含 `7连板 百花医药`、§2.5 `**7 板**`
- **v2.9.11（2026-08-10）**：**§4 板块分类收盘后重分类事故**——8/10 18:11 采集 16 板块生成报告，用户反馈 §4 与页面不符；19:06 重采发现页面已变 14 板块（99 股全同，67 只归类变化）。修复：重采 zthis → `fupan_oneclick.py --date 2026-08-10` 重生成 → verify 0 失败。经验入故障排查表（收盘后 18:00-19:00 板块分类可能延迟稳定）
- **v2.9.10（2026-08-06）**：`dashboard_gen.py` 已删除（用户批准，防文件污染）——scripts 目录干净，无停用残留文件
- **v2.9.9（2026-08-06，撤销串联）**：
  - **fupan 与 review-dashboard 分离，各做各的事**：fupan_oneclick.py 移除 Step 4 看板生成（当日 + 补生成模式都不再调 dashboard_gen）；`--skip-dashboard` 参数移除
  - 原因：dashboard_gen.py 自动渲染质量不达标（情绪宫格 4 处缺陷：今日封板率/昨连板表现/炸板数显示「—」（§2.1 键名"封板率"≠"今日封板率"、面板末行 3 列被过滤、炸板数不在面板键内）、昨涨停表现缺 + 号；且无手工版描述性标题文案）
  - 看板流程恢复：跑完 fupan 后调 review-dashboard skill 手工渲染（8/6 已恢复手工版 20260806_复盘看板claude.html）
  - `dashboard_gen.py` 保留但不执行（标注已停用）；**zthis 双份保护保留**（opencli_fetch 双写 + gen_report 双读，与看板无关，是数据安全加固）
- **v2.9.8（2026-08-06）**：
  - **fupan + review-dashboard 串联成完整流程**：新增 `dashboard_gen.py`（review-dashboard skill 固化）——解析报告 md 全部模块（指数/全球/情绪 12 宫格/涨跌停/连板/晋级率/TOP15/题材 13 卡全量/板块涨跌/资金/跌停/炸板/总结）→ 渲染交互式 HTML 看板（V2 单列全宽题材卡、左浮动 TOC、红涨绿跌、折叠 JS），**全量铁律：md 多少条渲染多少条**
  - fupan_oneclick.py Step 4：verify 后自动生成看板（当日 + `--date` 补生成模式都含）；`--skip-dashboard` 跳过；本进程 stdout reconfigure UTF-8（补生成直接 print gen_report 的 ✅ 输出 GBK 崩）
  - **zthis_sectors.json 双份保护**（8/6 Desktop 版消失事故：补生成时 §4 全空、报告缩水 30KB→11KB）：opencli_fetch.py zthis 写 Desktop + scripts 双份；gen_report.py 双路径读（Desktop 优先 → scripts 兜底）
  - 验证基准：8/6 全链重跑 ✅ verify 0 失败 / 看板 13 卡 79 股全量 / 报告 29.9KB §4 完整
- **v2.9.7（2026-08-06，8/6 正式盘后运行修复 6 个 bug，35/35 通过）**：
  - **重大事故修复：verify_report.py `from gen_report import _emotion_fallbacks` import 副作用** — import 会执行 gen_report 整个顶层代码，无 `--vision-snapshot` 时 `_e=None` → **用 qxlive 8/5 缓存（95/505/3725/1621/5.39/5.04）重新生成报告并覆盖 76 正确报告**（报告 mtime 晚于 gen_report 完成 1.8s 是识别线索）。修复：verify 不再 import gen_report，改为 `_eo_data is None` 判断 fallback；gen_report 加**无 snapshot 总闸**（`if not _vision_snap_path: FATAL`，铁律 3 落实到代码）
  - fupan_run.py `run()` 补 `encoding='utf-8', errors='replace'`（GBK 读线程 UnicodeDecodeError → r.stdout=None → TypeError）——fupan_oneclick/verify 已修，fupan_run 漏网
  - opencli_fetch.py vision 采集 HSLN 去"亿"单位（SKILL.md A1 铁律落实：`主力流入：-383亿` → `-383`，否则 gen_report float() ValueError）
  - verify_report.py 期望值 float 尾缀修复：`str(76.0)='76.0'` ≠ 报告 `**76**` → QX/HSLN 统一 `{:g}` 格式化（76.0→'76'、-383.0→'-383'；8/5 恰好整数/正数侥幸通过）
  - gen_report.py stdout UTF-8 reconfigure（Windows GBK 控制台 ✅ emoji print 崩 exit=1，报告已写但退出码误导）
  - fupan_oneclick.py `ensure_bridge` 两阶段拉起：daemon 未响应 → `opencli doctor` lazy 启动（8/6 实测冷启动 9s 拉起）→ 扩展未连 → Chrome `--load-extension`（实测 12s 重连）
- **v2.9.6（2026-08-06）**：
  - **新增 `fupan_oneclick.py` 一键脚本**：桥接自检（未连自动拉起 Chrome `--load-extension`，注意**不要加 `--remote-debugging-port=0`**——会致 Chrome 退出）→ vision 采集 → zthis 全量 → fupan_run 主编排 → verify；`--date` 补生成模式（跳过采集防跨日错配）；Chrome 路径多候选探测（用户级安装 `AppData\Local\Google\Chrome`）
  - gen_report.py 新增 `--date YYYY-MM-DD` 补生成历史报告（BJT 跨日时防错配：凌晨补昨日报告必须带，否则按今天生成 8/6 报告却用 8/5 snapshot = 脏数据）
  - 修错字："连拖家数" → "连板家数"、"昨连拖表现" → "昨连板表现"（报告输出侧；qxlive 端点原始字段名不动）
  - verify_report.py：`subprocess.run` 显式 `encoding='utf-8', errors='replace'` + `sys.executable`（消除 GBK 读线程 traceback）
  - 事故记录：8/6 00:02 生成 20260806_收盘复盘.md 用 8/5 snapshot → 已改名 `_DISCARD.md` 标记
- **v2.9.5（2026-08-05）**：
  - 新增 A0.5 opencli 浏览器通道（daemon `/command` API：navigate + exec；`#qxiframe` 提取 11 情绪按钮；SPA 自动合成层 probe/generate/cascade/record 全失败勿用）
  - A2 全量采集：opencli 点 `#showhide`"全部展开"→ 单段 JS 全量生成 zthis_sectors.json（15 板块/103 股无截断，突破 browser_snapshot 9 row 限制）；原"单板块逐个展开"降级为 fallback
  - gen_report.py：①解析 snapshot 后写 emotion_vision.json（契约闭合）②§2.5 综合判断/LBGD/封板率 vision-first（修 qxlive 旧值 92 混入）③传 snapshot 解析失败 FATAL 退出（防静默污染）④§4 排版修正：4.1 热度 → 4.2 代表股明细 → 4.3 mermaid
  - verify_report.py：期望值 vision-first（emotion_vision.json → pool 兜底）；章节检查对齐 v2.9.x 结构（一~六+附录A/B+复盘总结）；删过时标注检查（5/10/20日、占位、追溯表 → §2.2 数据源列）
  - 验证基准：2026-08-05 完整版 35/35 通过
