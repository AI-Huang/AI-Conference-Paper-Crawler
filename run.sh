#!/usr/bin/env bash
#
# run.sh — crawl AI conference papers (CVF, IEEE Xplore, NeurIPS, PMLR …).
#
# Usage:
#   ./run.sh <CONFERENCE> <YEAR> [options]
#   ./run.sh CVPR 2026                     # metadata only -> MySQL (no PDFs)
#   ./run.sh CVPR 2026 --download          # also download PDFs
#   ./run.sh ICCV 2023 --day 2023-10-04
#   ./run.sh IROS 2024                     # IROS via IEEE Developer API
#   ./run.sh IROS 2024 --resume            # resume an interrupted IROS crawl
#   ./run.sh IROS 2024 --bg               # run in background, log to file
#   ./run.sh CVPR 2026 --max 10            # stop after ~10 papers (testing)
#   ./run.sh                               # discover & crawl every conference
#
# Options:
#   --download       Also download paper PDFs (default: metadata only).
#   --day <DATE>     Restrict to one conference day (e.g. 2026-06-05). [CVF only]
#   --resume         Resume an interrupted crawl from its saved checkpoint.
#                    Checkpoint is stored under crawl-jobs/<CONF>-<YEAR>/.
#   --jobdir <DIR>   Explicitly set Scrapy JOBDIR (implies resume if dir exists).
#   --bg             Run in background; log written to $DATA_DIR/logs/<slug>.log.
#                    Follow output with: tail -f <logfile>
#   --max <N>        Stop after roughly N items (sets CLOSESPIDER_ITEMCOUNT).
#   --log <LEVEL>    Scrapy log level (default INFO).
#   -h, --help       Show this help.
#
# IEEE Xplore conferences (IROS …) require IEEE_API_KEY in .env.
# Register for a free key at https://developer.ieee.org/
#
# Paper metadata is upserted into MySQL (configured via MYSQL_* in .env). Any
# downloaded PDFs and the HTTP cache are written under $CVF_DATA_DIR (default
# $HOME/Data/AI-Conference-Paper-Crawler), keeping runtime data out of source.

set -euo pipefail

# Run from the repository root regardless of where the script is invoked.
cd "$(dirname "$0")"

usage() {
    sed -n '5,32p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

CONF=""
YEAR=""
DAY=""
MAX=""
LOG_LEVEL="INFO"
DOWNLOAD=0
RESUME=0
BG=0
JOBDIR_OVERRIDE=""

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
    --resume)
        RESUME=1
        shift
        ;;
    --jobdir)
        JOBDIR_OVERRIDE="${2:?--jobdir requires a directory path}"
        shift 2
        ;;
    --bg)
        BG=1
        shift
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

# ---- Spider selection -------------------------------------------------------
# IEEE-family conferences use the 'ieee' spider; everything else uses 'cvf'.
IEEE_CONFS="IROS"
SPIDER="cvf"
CONF_UPPER="${CONF^^}"
for ieee_conf in $IEEE_CONFS; do
    if [[ "$CONF_UPPER" == "$ieee_conf" ]]; then
        SPIDER="ieee"
        break
    fi
done

# ---- JOBDIR (断点续传) -------------------------------------------------------
# Determine JOBDIR: explicit override > --resume auto-path > none.
slug="${CONF_UPPER:-all}"
[[ -n "$YEAR" ]] && slug="${slug}-${YEAR}"

JOBDIR=""
if [[ -n "$JOBDIR_OVERRIDE" ]]; then
    JOBDIR="$JOBDIR_OVERRIDE"
elif [[ "$RESUME" == "1" ]]; then
    JOBDIR="crawl-jobs/${slug}"
fi

# ---- Log file (后台模式) -----------------------------------------------------
# Log files go under $DATA_DIR/logs/ (Code-Data separation).
DATA_DIR="${CVF_DATA_DIR:-$HOME/Data/AI-Conference-Paper-Crawler}"
LOG_DIR="$DATA_DIR/logs"
LOG_FILE=""
if [[ "$BG" == "1" ]]; then
    mkdir -p "$LOG_DIR"
    LOG_FILE="$LOG_DIR/${slug}-$(date +%Y%m%d-%H%M%S).log"
fi

# ---- Build the scrapy command -----------------------------------------------
cmd=(uv run scrapy crawl "$SPIDER")
[[ -n "$CONF" ]] && cmd+=(-a "conf=$CONF")
[[ -n "$YEAR" ]] && cmd+=(-a "year=$YEAR")
[[ -n "$DAY" ]] && [[ "$SPIDER" == "cvf" ]] && cmd+=(-a "day=$DAY")
[[ "$DOWNLOAD" == "1" ]] && cmd+=(-a "download=1")
[[ -n "$MAX" ]] && cmd+=(-s "CLOSESPIDER_ITEMCOUNT=$MAX")
[[ -n "$JOBDIR" ]] && cmd+=(-s "JOBDIR=$JOBDIR")
cmd+=(-s "LOG_LEVEL=$LOG_LEVEL")

# ---- Summary ----------------------------------------------------------------
label_resume=""
if [[ -n "$JOBDIR" ]]; then
    if [[ -d "$JOBDIR" ]]; then
        label_resume=" [RESUMING from $JOBDIR]"
    else
        label_resume=" [checkpoint -> $JOBDIR]"
    fi
fi
pdf_label=$([[ $DOWNLOAD == 1 ]] && echo '[+PDF]' || echo '[metadata only]')
echo "Spider: $SPIDER | Crawling: ${CONF_UPPER:-<all>} ${YEAR:-} ${DAY:+(day $DAY)}${MAX:+ (max $MAX)} $pdf_label$label_resume"

# ---- Launch -----------------------------------------------------------------
if [[ "$BG" == "1" ]]; then
    # Run detached; stdout+stderr → log file (unbuffered via stdbuf).
    nohup stdbuf -oL -eL "${cmd[@]}" >> "$LOG_FILE" 2>&1 &
    PID=$!
    echo "Started in background (PID=$PID)"
    echo "Log:  $LOG_FILE"
    echo "Follow: tail -f $LOG_FILE"
    echo "Stop:   kill $PID"
else
    exec "${cmd[@]}"
fi
