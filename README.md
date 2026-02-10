# College Data Analysis

Interactive map and table for exploring UTR college tennis data with cost information.

## Quick Start

```sh
uv run --with streamlit --with pandas --with folium --with streamlit-folium \
  streamlit run map.py
```

Then open http://localhost:8501 in your browser.

## Features

- Interactive map with college markers (color = UTR rating, size = cost)
- Table syncs with map viewport - zoom/pan to filter visible colleges
- Sidebar filters for UTR range, cost range, division, and text search

## Data

Pre-processed college data is stored in `dist/utr_costs_df.pkl`. Source data and SQL scripts for regenerating it are in `data/` and `sql/`.
