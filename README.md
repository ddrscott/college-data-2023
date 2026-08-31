# College Data Analysis

Interactive map and table for exploring UTR college tennis data with cost information.

## Quick Start

```sh
uv run --with streamlit --with pandas --with numpy --with folium \
  --with streamlit-folium --with streamlit-js-eval \
  streamlit run map.py
```

Then open http://localhost:8501 in your browser.

The dependency list also lives in `map.py`'s PEP-723 header, so `uv run map.py`
resolves it on its own.

## Features

- Interactive map with college markers (color = UTR rating, size = cost)
- Table syncs with map viewport - zoom/pan to filter visible colleges
- Sidebar filters for UTR range, cost range, division, and text search
- **Distance filter:** enter a ZIP code and a mileage range to keep only
  colleges that far from it. The map centers on the ZIP, draws a dashed circle
  at the outer radius, and the table gains a `Miles` column. The slider's top
  stop (1000) means *no upper limit* - coast to coast is about 2800 miles, so a
  literal cap would quietly hide schools.
- Table grows to fill the remaining viewport height instead of showing ten rows

## Data

`dist/utr_costs_df.pkl` holds the 918 men's college tennis programs that have
both a UTR record and IPEDS cost data. Current sources:

| Source | File | Vintage |
| --- | --- | --- |
| IPEDS directory (name, location, website) | `data/hd2025.csv` | Fall 2025, released Jul 2026 |
| IPEDS charges (tuition, books, housing) | `data/cost1_2024.csv` | 2024-25, released Dec 2025 |
| UTR ratings, division | `data/utr-schools.json` | live |
| UTR roster/member counts | `data/utr-clubs.json` | live |
| Census ZCTA centroids (ZIP -> lat/lon) | `dist/zip_centroids.csv.gz` | 2020 gazetteer |

`data/` is gitignored - regenerate it with the fetch scripts below.
`dist/` is checked in: it is what the app and the Docker image actually read.

## Refreshing

```sh
./fetch_ipeds.sh                                   # IPEDS -> data/
uv run fetch_utr.py --index schools > data/utr-schools.json
uv run fetch_utr.py --index clubs   > data/utr-clubs.json
uv run refresh.py                                  # -> dist/utr_costs_df.pkl
uv run refresh.py --unmatched                      # UTR programs with no IPEDS match

./fetch_zips.sh                                    # -> dist/zip_centroids.csv.gz
```

`fetch_zips.sh` rarely needs rerunning - ZCTA centroids only move with the
decennial census.

### Gotchas worth knowing

- **IPEDS moved its downloads.** Files now live under
  `/ipeds/complete-data-files/`, not `/ipeds/datacenter/data/`. The tuition and
  cost-of-attendance items also left the Institutional Characteristics survey
  for a new **Cost (CST)** component, so `IC<year>_AY` is gone and
  `COST1_<year>` replaces it. `nces.ed.gov` frequently returns a 200-status
  "temporarily down" page, so `fetch_ipeds.sh` validates each zip and retries.
- **Directory and cost years differ.** The Fall 2025 collection (HD2025) is out
  but its cost component is not, so the newest charges available are 2024-25.
  Pass different years to `fetch_ipeds.sh` and edit the paths in `refresh.py`
  when that changes.
- **IPEDS encodings are inconsistent** - a mix of latin-1 and BOM-prefixed
  UTF-8 across years. `refresh.py` tries `utf-8-sig` then falls back to
  `latin1`; reading a BOM'd file as latin-1 yields a `ï»¿UNITID` column and a
  baffling "no such column" error downstream.
- **`refresh.py` pins pandas to 2.2.3** to match `requirements.txt`. A pickle
  written by pandas 3.x cannot be read by the 2.2.3 the app runs on - it fails
  with a `StringDtype.__init__()` argument error.
- **UTR restructured its search API.** `schoolClubSearch=true` still returns the
  clubs index with `memberCount`, but every `power6*` field on it is now null.
  Ratings come from the schools index instead, under
  `activeRosters[].power6`. No auth is needed - the `UTR_JWT` in `.env` expired
  in January 2025 and is no longer used.
- **Page the UTR API with `sort=id:asc`.** Without a sort the search silently
  returns duplicates and drops rows across page boundaries.
- **UTR's state field is wrong often enough to be useless** (Alma College,
  Michigan, is filed under AR), so name matching in `refresh.py` never uses it.
- **The ZCTA gazetteer is pipe-delimited despite its `.txt` name.** Parsing it
  as TSV produces a single-column file that looks plausible until every ZIP
  lookup misses.
- **PO-box-only ZIPs have no ZCTA** and so are absent from the centroid file.
  The app warns rather than failing.

## Table height

`st.dataframe` takes a pixel height and defaults to "at most ten rows". Forcing
the container taller with CSS does *not* work: glide-data-grid measures itself
once on mount and never re-reads the container, so the extra height renders as
dead space below the last row - the container grows, the canvas does not.

So `map.py` asks the browser for its height via `streamlit-js-eval` and passes a
computed pixel value. That call must read `parent.window.innerHeight`: the
component runs inside its own 8px iframe, where a bare `window.innerHeight`
returns 0 and silently falls back to the default, reproducing the original bug.

Below roughly 855px of viewport the 200px floor wins and the page scrolls a
little. The first paint uses a 420px default before the browser reports back.

## Matching UTR to IPEDS

`utr_crosswalk.csv` maps IPEDS `UNITID` to the UTR men's club id. It was built
once with embedding similarity plus hand review (see `dig-2.ipynb`) and is
checked in so that curation is never redone. `refresh.py` applies it first,
then fills gaps with exact and normalized name matches, accepting a match only
where the name is unambiguous on both sides.

About a hundred UTR programs still have no IPEDS counterpart - `University of
Washington` and `Tennessee Tech University` among them, whose names are too
ambiguous to match automatically. List them with `uv run refresh.py
--unmatched` and add confirmed pairs to `utr_crosswalk.csv`.

Source data and the original SQL/notebook exploration are in `data/`, `sql/`,
and the `dig*.ipynb` notebooks.

## Deployment

Public at https://colleges.dataturd.com, served from the Docker host at
http://192.168.68.10:8001 as a plain `docker run` container - no compose, no
volume mounts, code baked into the image. See [CLAUDE.md](CLAUDE.md) for the
rebuild steps and the traps (notably: `.dockerignore` excludes `data/`, so
runtime assets belong in `dist/`).

Plausible analytics is injected into Streamlit's prebuilt `index.html` by the
`Dockerfile`, since Streamlit exposes no hook for `<head>`. `st.markdown` strips
`<script>`, and `st.components.v1.html` would sandbox it in an iframe that
reports itself rather than the page. The build asserts the tag landed, so a
Streamlit upgrade that reshapes the template fails the build instead of
quietly shipping without analytics.

```sh
ssh spierce@192.168.68.10 docker ps | grep college
```
