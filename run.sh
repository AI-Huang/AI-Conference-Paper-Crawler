#!/usr/bin/env bash
#
# run.sh — crawl AI conference papers from the CVF open-access site.
#
# Usage:
#   ./run.sh <CONFERENCE> <YEAR> [options]
#   ./run.sh CVPR 2026                     # metadata only -> MySQL (no PDFs)
#   ./run.sh CVPR 2026 --download          # also download PDFs
#   ./run.sh ICCV 2023 --day 2023-10-04
#   ./run.sh CVPR 2026 --max 10            # stop after ~10 papers (testing)
#   ./run.sh                               # discover & crawl every conference
#
# Options:
#   --download       Also download paper PDFs (default: metadata only).
#   --day <DATE>     Restrict to one conference day (e.g. 2026-06-05).
#   --max <N>        Stop after roughly N items (sets CLOSESPIDER_ITEMCOUNT).
#   --log <LEVEL>    Scrapy log level (default INFO).
#   -h, --help       Show this help.
#
# Paper metadata is upserted into MySQL (configured via MYSQL_* in .env). Any
# downloaded PDFs and the HTTP cache are written under $CVF_DATA_DIR (default
# $HOME/Data/AI-Conference-Paper-Crawler), keeping runtime data out of source.

set -euo pipefail

# Run from the repository root regardless of where the script is invoked.
cd "$(dirname "$0")"

usage() {
    sed -n '5,18p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

CONF=""
YEAR=""
DAY=""
MAX=""
LOG_LEVEL="INFO"
DOWNLOAD=0

# First one or two positional args are conference and year.
if [[ "${1:-}" =~ ^[A-Za-z]+$ ]]; then
    CONF="$1"
    shift
    if [[ "${1:-}" =~ ^[0-9]{4}$ ]]; then
        YEAR="$1"
        shift
    fi
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
    --download)
        DOWNLOAD=1
        shift
        ;;
    --day)
        DAY="${2:?--day requires a date}"
        shift 2
        ;;
    --max)
        MAX="${2:?--max requires a number}"
        shift 2
        ;;
    --log)
        LOG_LEVEL="${2:?--log requires a level}"
        shift 2
        ;;
    -h | --help)
        usage 0
        ;;
    *)
        echo "Unknown argument: $1" >&2
        usage 1
        ;;
    esac
done

# Build the scrapy command.
cmd=(uv run scrapy crawl cvf)
[[ -n "$CONF" ]] && cmd+=(-a "conf=$CONF")
[[ -n "$YEAR" ]] && cmd+=(-a "year=$YEAR")
[[ -n "$DAY" ]] && cmd+=(-a "day=$DAY")
[[ "$DOWNLOAD" == "1" ]] && cmd+=(-a "download=1")
[[ -n "$MAX" ]] && cmd+=(-s "CLOSESPIDER_ITEMCOUNT=$MAX")
cmd+=(-s "LOG_LEVEL=$LOG_LEVEL")

echo "Crawling: ${CONF:-<all>} ${YEAR:-} ${DAY:+(day $DAY)}${MAX:+ (max $MAX)} ${DOWNLOAD:+}$([[ $DOWNLOAD == 1 ]] && echo '[+PDF]' || echo '[metadata only]')"
exec "${cmd[@]}"
