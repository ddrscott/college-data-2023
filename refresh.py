# /// script
# dependencies = ["duckdb", "pandas==2.2.3"]
# ///
"""Rebuild dist/utr_costs_df.pkl from IPEDS + UTR source data.

pandas is pinned to match requirements.txt: map.py unpickles this file, and a
frame written by pandas 3.x cannot be read by the 2.2.3 the app runs on.

Inputs (see README for download URLs):
    data/hd2025.csv        IPEDS directory -- name, location, web address
    data/cost1_2024.csv    IPEDS Cost component -- tuition, books, housing
    data/utr-schools.json  UTR schools index -- power6 ratings, division
    data/utr-clubs.json    UTR clubs index   -- memberCount
    utr_crosswalk.csv      curated IPEDS UNITID <-> UTR men's club id map

The crosswalk is the expensive artifact: it was built once with embedding
similarity plus hand review, so it is checked in and reused rather than
recomputed. New UTR programs are matched by exact name + state only; anything
left over is reported for manual addition to the crosswalk.

Usage:
    uv run refresh.py
    uv run refresh.py --unmatched     # list UTR programs with no IPEDS match
"""
import argparse
import json
import pickle
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd

DATA = Path("data")
HD = DATA / "hd2025.csv"
COST = DATA / "cost1_2024.csv"
SCHOOLS = DATA / "utr-schools.json"
CLUBS = DATA / "utr-clubs.json"
CROSSWALK = Path("utr_crosswalk.csv")
OUT_PKL = Path("dist/utr_costs_df.pkl")
OUT_CSV = DATA / "utr_costs.csv"


def utr_frame() -> pd.DataFrame:
    """One row per men's college program, keyed by men's club id."""
    schools = json.loads(SCHOOLS.read_text())["hits"]
    rows = []
    for hit in schools:
        src = hit["source"]
        rosters = [
            r for r in (src.get("activeRosters") or [])
            if (r.get("club") or {}).get("subType") == "mens" and r.get("power6")
        ]
        # Most recent season wins if a school somehow has more than one.
        rosters.sort(key=lambda r: (r.get("season") or {}).get("id", 0), reverse=True)
        p6 = rosters[0]["power6"] if rosters else {}
        location = src.get("location") or {}
        display = location.get("display") or ""
        rows.append({
            "utr_id": src.get("mensClubId") or 0,
            "utr_name": src.get("name"),
            "utr_state": display.rsplit(", ", 1)[-1] if ", " in display else None,
            "power6": p6.get("power6Rating"),
            "power6High": p6.get("power6HighRating"),
            "power6Low": p6.get("power6LowRating"),
            "divisionName": ((src.get("conference") or {}).get("division") or {}).get("divisionName"),
        })
    utr = pd.DataFrame(rows)
    utr = utr[utr["utr_id"] > 0].drop_duplicates("utr_id")

    clubs = json.loads(CLUBS.read_text())["hits"]
    counts = pd.DataFrame(
        [{"utr_id": h["source"]["id"], "memberCount": h["source"].get("memberCount")} for h in clubs]
    ).drop_duplicates("utr_id")
    return utr.merge(counts, on="utr_id", how="left")


def read_ipeds(path: Path) -> pd.DataFrame:
    """IPEDS ships a mix of latin-1 and BOM-prefixed UTF-8 across years."""
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin1", low_memory=False)


def costs_frame(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    schools = read_ipeds(HD)  # noqa: F841
    charges = read_ipeds(COST)  # noqa: F841
    return conn.sql(r"""
        WITH data AS (
            SELECT
                schools.unitid AS college_id,
                trim(INSTNM) AS college_name,
                trim(IALIAS) AS short_name,
                city AS city,
                stabbr AS state,
                LATITUDE::float AS latitude,
                LONGITUD::float AS longitude,
                WEBADDR AS url,
                try_cast(CHG2AY3 AS DECIMAL(10,2)) AS instate_tuition,
                try_cast(CHG3AY3 AS DECIMAL(10,2)) AS outstate_tuition,
                try_cast(CHG4AY3 AS DECIMAL(10,2)) AS books,
                try_cast(CHG5AY3 AS DECIMAL(10,2)) AS housing,
                try_cast(CHG6AY3 AS DECIMAL(10,2)) AS other_expenses,
            FROM schools
            JOIN charges ON schools.UNITID = charges.UNITID
        )
        SELECT
            *,
            coalesce(outstate_tuition, 0) + coalesce(books, 0)
                + coalesce(housing, 0) + coalesce(other_expenses, 0) AS total_outstate,
            coalesce(instate_tuition, 0) + coalesce(books, 0)
                + coalesce(housing, 0) + coalesce(other_expenses, 0) AS total_instate,
        FROM data
    """).to_df()


def _unique(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    """Rows whose key appears exactly once -- an unambiguous match candidate."""
    counts = frame[key].value_counts()
    return frame[frame[key].isin(counts[counts == 1].index)]


def _normalize(name: str) -> str:
    """Collapse the punctuation and boilerplate IPEDS and UTR disagree on.

    'University of Nevada, Las Vegas' and 'University of Nevada-Las Vegas'
    both reduce to 'nevada las vegas'.
    """
    text = re.sub(r"\b(the|university|univ|college|of|at|main campus|campus)\b", " ", name.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def resolve(costs: pd.DataFrame, utr: pd.DataFrame) -> pd.DataFrame:
    """Attach a utr_id to each IPEDS school.

    The checked-in crosswalk wins. Anything left over is matched on name, first
    verbatim and then normalized, and only where the name is unambiguous on
    both sides -- UTR's own state field is wrong often enough (Alma College,
    Michigan, is filed under AR) to be useless as a tiebreaker.
    """
    crosswalk = pd.read_csv(CROSSWALK)[["college_id", "utr_id"]]
    crosswalk = crosswalk[crosswalk["utr_id"].isin(set(utr["utr_id"]))]
    costs = costs.merge(crosswalk, on="college_id", how="left")

    for label, key in (("exact", "college_name"), ("normalized", "_norm")):
        free_utr = utr[~utr["utr_id"].isin(set(costs["utr_id"].dropna()))][["utr_id", "utr_name"]].copy()
        free_costs = costs[costs["utr_id"].isna()][["college_id", "college_name"]].copy()
        if key == "_norm":
            free_utr["_norm"] = free_utr["utr_name"].map(_normalize)
            free_costs["_norm"] = free_costs["college_name"].map(_normalize)
            left, right = "_norm", "_norm"
        else:
            left, right = "utr_name", "college_name"

        matches = _unique(free_utr, left).merge(
            _unique(free_costs, right), left_on=left, right_on=right
        )
        if matches.empty:
            continue
        fill = costs["college_id"].map(matches.set_index("college_id")["utr_id"])
        costs["utr_id"] = costs["utr_id"].fillna(fill)
        print(f"matched {len(matches)} programs by {label} name", file=sys.stderr)

    return costs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unmatched", action="store_true",
                        help="print UTR programs with no IPEDS match and exit")
    args = parser.parse_args()

    conn = duckdb.connect(":memory:")
    utr = utr_frame()
    costs = resolve(costs_frame(conn), utr)

    if args.unmatched:
        missing = utr[~utr["utr_id"].isin(set(costs["utr_id"].dropna()))]
        missing.sort_values(["utr_state", "utr_name"]).to_csv(sys.stdout, index=False)
        return

    df = costs.merge(utr, on="utr_id", how="inner")
    df = df[df["housing"].notna()]
    df = df[[
        "college_id", "college_name", "short_name", "city", "state",
        "latitude", "longitude", "url",
        "instate_tuition", "outstate_tuition", "books", "housing", "other_expenses",
        "total_outstate", "total_instate",
        "utr_id", "power6", "power6High", "power6Low", "divisionName", "memberCount",
    ]].copy()
    df["utr_id"] = df["utr_id"].astype("int32")
    for col in ("power6", "power6High", "power6Low"):
        df[col] = df[col].astype(float).fillna(0.0)
    df["memberCount"] = df["memberCount"].fillna(0).astype("int64")
    for col in ("instate_tuition", "outstate_tuition", "books", "housing",
                "other_expenses", "total_outstate", "total_instate"):
        df[col] = df[col].astype(float)
    df = df.sort_values("college_id").reset_index(drop=True)

    OUT_PKL.parent.mkdir(exist_ok=True)
    pickle.dump(df, open(OUT_PKL, "wb"))
    df.to_csv(OUT_CSV, index=False)
    print(f"wrote {OUT_PKL} and {OUT_CSV}: {len(df)} colleges", file=sys.stderr)


if __name__ == "__main__":
    main()
