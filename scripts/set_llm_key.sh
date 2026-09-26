#!/usr/bin/env bash
# 安全地把 LLM API key 写进 .env（输入不回显，不进 shell 历史）
set -euo pipefail
cd "$(dirname "$0")/.."
read -rsp "粘贴 API key 后回车: " KEY; echo
[ -n "$KEY" ] || { echo "空的，未修改"; exit 1; }
python3 - "$KEY" <<'PY'
import re, sys
p = ".env"; s = open(p).read()
s = re.sub(r"^LLM_API_KEY=.*$", "LLM_API_KEY=" + sys.argv[1], s, flags=re.M)
open(p, "w").write(s)
PY
echo "已写入 .env（长度 ${#KEY}）"
