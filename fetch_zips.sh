#!/bin/bash -eu
#
# Build dist/zip_centroids.csv.gz from the Census ZCTA gazetteer.
#
# ZCTAs are the Census Bureau's approximation of USPS ZIP codes - close enough
# to anchor a "within N miles" search, and public domain with no API key or
# runtime network call. PO-box-only ZIPs have no ZCTA and so will not resolve.
#
# This lands in dist/ rather than data/ because the app reads it at runtime and
# .dockerignore excludes data/.
#
# Usage: ./fetch_zips.sh [year]

YEAR="${1:-2025}"
URL="https://www2.census.gov/geo/docs/maps-data/data/gazetteer/${YEAR}_Gazetteer/${YEAR}_Gaz_zcta_national.zip"
ROOT="$(dirname "$0")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -sSL --max-time 300 -A "Mozilla/5.0" -o "$TMP/gaz.zip" "$URL"
unzip -oq "$TMP/gaz.zip" -d "$TMP"

# The ZCTA gazetteer is PIPE-delimited despite the .txt name, and INTPTLONG
# carries leading padding. GEOID, INTPTLAT and INTPTLONG are columns 1, 7, 8.
# Four decimal places is ~11m - far finer than a mile-radius search needs, and
# it more than halves the file.
{
    echo "zip,latitude,longitude"
    awk -F'|' 'NR > 1 && $7 != "" { printf "%s,%.4f,%.4f\n", $1, $7, $8 }' \
        "$TMP/${YEAR}_Gaz_zcta_national.txt"
} | gzip -9 > "$ROOT/dist/zip_centroids.csv.gz"

echo "wrote dist/zip_centroids.csv.gz ($(gzip -dc "$ROOT/dist/zip_centroids.csv.gz" | tail -n +2 | wc -l | tr -d ' ') zips)"
