#!/bin/bash -eu
#
# Download the IPEDS complete data files refresh.py needs into data/.
#
# NCES moved these off /ipeds/datacenter/data/ onto /ipeds/complete-data-files/,
# and split the old IC_AY charges file into a separate Cost (CST) component
# published as COST1_<year>. The datacenter host also drops connections under
# load and answers with a 200-status "temporarily down" page, so every file is
# retried and validated as a zip rather than trusted by HTTP status.
#
# Usage: ./fetch_ipeds.sh [directory-year] [cost-year]

BASE="https://nces.ed.gov/ipeds/complete-data-files"
DIR_YEAR="${1:-2025}"
COST_YEAR="${2:-2024}"
OUT="$(dirname "$0")/data"

mkdir -p "$OUT"

fetch() {
    local name="$1" zip="$OUT/$1.zip"
    for attempt in 1 2 3 4 5; do
        curl -sSL --max-time 300 -A "Mozilla/5.0" -o "$zip" "$BASE/$name.zip" 2>/dev/null || true
        if unzip -tq "$zip" >/dev/null 2>&1; then
            unzip -oq "$zip" -d "$OUT"
            echo "$name ok"
            return 0
        fi
        sleep 3
    done
    echo "$name FAILED after 5 attempts (nces.ed.gov is flaky; just rerun)" >&2
    rm -f "$zip"
    return 1
}

fetch "HD${DIR_YEAR}"
fetch "COST1_${COST_YEAR}"
