#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Dedicated review database; no exchange keys needed and no Telegram messages.
export V17_MODE=paper V17_DEMO_ONLY=0 LIVE_TRADING_ENABLED=0 V17_TELEGRAM=0
export OPS_DB=runtime/v17_review_paper.db
python -m v17_ops "$@" --mode paper
