#!/usr/bin/env bash
set -euo pipefail
URL="${1:-http://127.0.0.1:5000/}"
ZAP_HOME="${ZAP_HOME:-/home/ubuntu/zap}"
OUT_DIR="${OUT_DIR:-qa/zap}"
mkdir -p "$OUT_DIR"
"$ZAP_HOME/zap.sh" -cmd -silent -quickurl "$URL" -quickout "$OUT_DIR/zap-report.html" -quickprogress 2>&1 | tee "$OUT_DIR/zap-console.log"
