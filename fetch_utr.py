# /// script
# dependencies = ["httpx"]
# ///
"""Fetch UTR college data to stdout as JSON.

UTR restructured its search API some time after the original 2024 pull:

  * ``schoolClubSearch=true`` searches the *clubs* index. It still returns one
    hit per team (men's and women's are separate clubs) with ``memberCount``,
    but every ``power6*`` field now comes back null.
  * Without that flag the endpoint searches the *schools* index, where each hit
    carries ``activeRosters[].power6`` -- the current team rating, its high and
    its low. No authentication required.

``mensClubId`` on a school hit is the same id the clubs index uses, and the
same id the ``utr_id`` crosswalk was built against, so the two indexes join
cleanly.

Usage:
    uv run fetch_utr.py --index schools > data/utr-schools.json
    uv run fetch_utr.py --index clubs   > data/utr-clubs.json
"""
import argparse
import json
import sys
import time

import httpx

BASE = "https://api.utrsports.net/v2/search/colleges"
PAGE = 100


def fetch(index: str, gender: str, page_size: int) -> dict:
    # `sort` is required for stable paging -- without it the underlying search
    # returns duplicates and silently drops rows across page boundaries.
    params = {"gender": gender, "sort": "id:asc"}
    if index == "clubs":
        params |= {"utrType": "verified", "utrTeamType": "singles", "schoolClubSearch": "true"}

    hits: list[dict] = []
    total = None
    skip = 0
    headers = {"user-agent": "Mozilla/5.0", "accept": "application/json"}
    with httpx.Client(timeout=60, headers=headers) as client:
        while total is None or skip < total:
            resp = client.get(BASE, params=params | {"top": page_size, "skip": skip})
            resp.raise_for_status()
            data = resp.json()
            if total is None:
                total = data["total"]
                print(f"{index}: {total} total", file=sys.stderr)
            batch = data.get("hits") or []
            if not batch:
                break
            hits.extend(batch)
            skip += len(batch)
            print(f"  {skip}/{total}", file=sys.stderr)
            time.sleep(0.2)

    seen = {h["source"]["id"] for h in hits}
    if len(seen) != len(hits):
        print(f"WARNING: {len(hits) - len(seen)} duplicate ids", file=sys.stderr)
    return {"total": total, "index": index, "gender": gender, "hits": hits}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", default="schools", choices=["schools", "clubs"])
    parser.add_argument("--gender", default="M", choices=["M", "W"])
    parser.add_argument("--page-size", type=int, default=PAGE)
    args = parser.parse_args()
    json.dump(fetch(args.index, args.gender, args.page_size), sys.stdout)


if __name__ == "__main__":
    main()
