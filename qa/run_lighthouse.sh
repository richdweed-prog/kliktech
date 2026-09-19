#!/usr/bin/env bash
set -euo pipefail
URL="${1:-http://127.0.0.1:5000/}"
OUT_DIR="${OUT_DIR:-qa/lighthouse}"
mkdir -p "$OUT_DIR"
npx --yes lighthouse "$URL" --output=json --output=html --output-path="$OUT_DIR/report" --chrome-flags="--headless --no-sandbox --disable-gpu"
