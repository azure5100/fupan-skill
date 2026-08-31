#!/usr/bin/env bash
# fupan skill — one-shot data pull
# Pulls all 10 JSON files from 短线侠 into the current working directory.
# Run from Desktop (where gen_report.py expects them).
#
# Usage:  bash scripts/pull_data.sh

set -e

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BASE="https://www.duanxianxia.com"

echo "=== Pulling 短线侠 JSON snapshots to $(pwd) ==="

# v2.4.1: 先清上次的临时 JSON 快照 (保留 emotion_vision.json 和 zthis_sectors.json)
_TEMP_JSON="ztpool.json zbpool.json dtpool.json lbpool.json czpool.json dmpool.json fxpool.json global.json qxlive.json jinji.json"
_cleaned=0
for f in $_TEMP_JSON; do
  if [ -f "$f" ]; then
    rm -f "$f"
    _cleaned=$((_cleaned+1))
  fi
done
if [ "$_cleaned" -gt 0 ]; then
  echo "[v2.4.1] 自动清理上次的临时 JSON: ${_cleaned} 个"
fi

# Global indices (20 items: A-share / HK / US / commodities / FX)
curl -sL --max-time 10 -A "$UA" "$BASE/vendor/stockdata/global.json" -o global.json
echo "  global.json     $(wc -c < global.json) bytes"

# 晋级率 HTML (1→2, 2→3, 3→4, 7→8 等)
curl -sL --max-time 10 -A "$UA" "$BASE/vendor/stockdata/jinjidata.json" -o jinji.json
echo "  jinji.json      $(wc -c < jinji.json) bytes"

# 题材情绪 13-channel time series (last value = current snapshot)
curl -sL --max-time 10 -A "$UA" "$BASE/api/getLastQxlive" -o qxlive.json
echo "  qxlive.json     $(wc -c < qxlive.json) bytes"

# 7 pools: 涨停/炸板/跌停/连扳/冲涨/大面/热门
for ep in zt zb dt lb cz dm fx; do
  Ep=$(echo "$ep" | awk '{print toupper(substr($0,1,1)) substr($0,2)}')
  curl -sL --max-time 10 -A "$UA" "$BASE/data/get${Ep}PoolData/" -o "${ep}pool.json"
  echo "  ${ep}pool.json   $(wc -c < ${ep}pool.json) bytes"
done

echo ""
echo "=== Done. Now run:  python scripts/gen_report.py ==="
