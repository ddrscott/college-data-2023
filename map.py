# /// script
# dependencies = [
#   "streamlit",
#   "streamlit-js-eval",
#   "numpy",
#   "pandas",
#   "folium",
#   "streamlit-folium",
# ]
# ///

import os
import numpy as np
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval

DATA_FILE = os.getenv('DATA_FILE', 'dist/utr_costs_df.pkl')
ZIP_FILE = os.getenv('ZIP_FILE', 'dist/zip_centroids.csv.gz')

# The distance slider's top stop means "no upper limit" - coast to coast is
# about 2800 miles, so a literal 1000 mile cap would quietly hide schools.
MAX_MILES = 1000
EARTH_RADIUS_MILES = 3958.8

MAP_HEIGHT = 500
# Page padding, the gap between elements and a little breathing room at the
# bottom - everything the table has to share the viewport with besides the map.
TABLE_CHROME = 155
MIN_TABLE_HEIGHT = 200
# Used for the first paint, before the browser reports its height.
DEFAULT_TABLE_HEIGHT = 420

st.set_page_config(page_title="College Tennis Map", layout="wide")

# Streamlit pads the page generously enough to push the table off the bottom.
st.markdown(
    """<style>
    [data-testid="stMainBlockContainer"] { padding-top: 2rem; padding-bottom: 1rem; }
    </style>""",
    unsafe_allow_html=True,
)


def table_height() -> int:
    """Pixels of viewport left over for the table once the map has its share.

    st.dataframe wants a pixel height and defaults to showing ten rows. Forcing
    the container taller in CSS does not work: the grid measures itself once on
    mount and never re-reads the container, so the extra height renders as dead
    space below the last row. Hence asking the browser how tall it is.
    """
    # The component runs inside its own tiny iframe, so this has to reach up to
    # the real window - `window.innerHeight` here would report the iframe's 8px.
    viewport = streamlit_js_eval(js_expressions='parent.window.innerHeight', key='viewport_height')
    if not viewport:
        return DEFAULT_TABLE_HEIGHT
    return max(MIN_TABLE_HEIGHT, int(viewport) - MAP_HEIGHT - TABLE_CHROME)


@st.cache_data
def utr_cost_data():
    import pickle
    from io import StringIO

    with open(DATA_FILE, 'rb') as f:
        df = pickle.load(f)
        return pd.read_json(StringIO(df.to_json()))

@st.cache_data
def zip_centroids():
    """ZIP -> lat/lon, from the Census ZCTA gazetteer. See fetch_zips.sh."""
    return pd.read_csv(ZIP_FILE, dtype={'zip': str}).set_index('zip')


def miles_from(lat: float, lon: float, lats: pd.Series, lons: pd.Series) -> pd.Series:
    """Great-circle distance in miles from one point to many."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat, lon, lats, lons))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def distance_filter(df: pd.DataFrame):
    """Filter to colleges a given distance from a ZIP code.

    Returns the filtered frame plus the origin, so the map can recenter on it.
    """
    side = st.sidebar
    zipcode = side.text_input("ZIP Code", max_chars=5, placeholder="e.g. 90210").strip()
    miles = side.slider(
        "Miles from ZIP", min_value=0, max_value=MAX_MILES, step=10, value=(0, 100),
        help=f"{MAX_MILES} means no upper limit.",
    )

    if not zipcode:
        return df, None
    if not zipcode.isdigit() or len(zipcode) != 5:
        side.warning("Enter a 5-digit ZIP code.")
        return df, None

    centroids = zip_centroids()
    if zipcode not in centroids.index:
        # PO-box-only ZIPs have no ZCTA and so are absent from the gazetteer.
        side.warning(f"No location on file for ZIP {zipcode}.")
        return df, None

    origin = centroids.loc[zipcode]
    df = df.copy()
    df['distance'] = miles_from(origin.latitude, origin.longitude, df['latitude'], df['longitude'])

    low, high = miles
    keep = df['distance'] >= low
    if high < MAX_MILES:
        keep &= df['distance'] <= high
    df = df[keep]

    limit = "any distance" if high >= MAX_MILES else f"{high} miles"
    side.caption(f"{len(df)} within {limit} of {zipcode}" + (f" (beyond {low})" if low else ""))
    return df, (float(origin.latitude), float(origin.longitude), low, high)


def filter_dataframe(df: pd.DataFrame):
    side = st.sidebar
    # Slider bounds come from the whole dataset, not the distance-filtered
    # frame: they stay put as the ZIP changes, and an empty result would
    # otherwise hand the sliders NaN bounds and blow up.
    limits = df
    df, origin = distance_filter(df)

    min_utr = 0.0
    max_utr = float(limits['power6Low'].max())
    utr_range = side.slider("UTR Filter", min_value=min_utr, max_value=max_utr, step=0.1, value=(min_utr, max_utr))

    min_outstate = int(limits['total_outstate'].min())
    max_outstate = int(limits['total_outstate'].max())
    if outstate_range := side.slider("Out of State Costs", min_value=min_outstate, max_value=max_outstate, step=500, value=(min_outstate, max_outstate)):
        df = df[df['total_outstate'].between(*outstate_range)]


    total = df['total_outstate'].count()
    # Filter the DataFrame based on the UTR range
    df = df[df['power6Low'].between(*utr_range)] # type: ignore

    if search_text := side.text_input("Text Search"):
        df = df[df.apply(lambda row: row.astype(str).str.contains(search_text, regex=True).any(), axis=1)] # type: ignore

    side.write("Division")
    divisions = df['divisionName'].value_counts()
    selected_divisions = []
    if divisions.size > 1:
        for division, count in divisions.items():
            if side.checkbox(f"{division} ({count})", key=division): # type: ignore
                selected_divisions.append(division)

    if selected_divisions:
        df = df[df['divisionName'].isin(selected_divisions)]  # type: ignore

    side.write("Filtered: %s of %s" % (len(df), total))


    side.info("- Blue indicates lower UTR\n- Red indicates higher UTR\n- Larger radius indicates higher cost")

    # Calculate minimum and maximum values for 'total_cost' in the filtered data
    min_total_cost = df['total_outstate'].min()
    max_total_cost = df['total_outstate'].max()

    def get_color(power6Low):
        normalized_value = (power6Low - utr_range[0]) / (utr_range[1] - utr_range[0])
        blue_component = int((1.0 - normalized_value) * 255)
        red_component = int(normalized_value * 255)
        return [red_component, 0, blue_component, 180]

    def get_radius(total_cost):
        try:
            # Normalize total cost to the desired radius range (e.g., 5 to 50)
            normalized_value = (total_cost - min_total_cost) / (max_total_cost - min_total_cost)
            radius_range_min = 5
            radius_range_max = 100
            return int(normalized_value * (radius_range_max - radius_range_min) + radius_range_min)
        except Exception as e:
            return 5

    # Apply functions to create new columns 'color' and 'radius'
    df['color'] = df['power6Low'].apply(get_color)
    df['radius'] = df['total_outstate'].apply(get_radius)

    return df, origin

def zoom_for(miles: int) -> int:
    """Roughly fit a radius in miles to a Leaflet zoom level."""
    for limit, zoom in ((25, 9), (50, 8), (100, 7), (250, 6), (500, 5)):
        if miles <= limit:
            return zoom
    return 4


def main():
    filtered, origin = filter_dataframe(utr_cost_data())

    if origin:
        lat, lon, _, high = origin
        map_center, zoom = [lat, lon], zoom_for(high)
    elif len(filtered):
        map_center, zoom = [filtered['latitude'].mean(), filtered['longitude'].mean()], 4
    else:
        # Nothing left to average - fall back to a view of the whole country.
        map_center, zoom = [39.8, -98.6], 4

    # Create Folium map
    m = folium.Map(
        location=map_center,
        zoom_start=zoom,
        tiles='cartodbpositron'
    )

    if origin:
        lat, lon, low, high = origin
        for miles in (low, high if high < MAX_MILES else None):
            if miles:
                folium.Circle(
                    location=[lat, lon], radius=miles * 1609.34,
                    color='#666', weight=1, fill=False, dash_array='4',
                ).add_to(m)

    # Add CircleMarkers for each college
    for _, row in filtered.iterrows():
        color = row['color']
        folium.CircleMarker(
            location=[row['latitude'], row['longitude']],
            radius=max(3, row['radius'] / 10),
            color=f"rgb({color[0]},{color[1]},{color[2]})",
            fill=True,
            fill_color=f"rgb({color[0]},{color[1]},{color[2]})",
            fill_opacity=0.7,
            tooltip=row['college_name'],
            popup=folium.Popup(
                f"<b>{row['college_name']}</b><br>"
                f"UTR: {row['power6Low']}<br>"
                f"${row['total_outstate']:,.0f}",
                max_width=300
            ),
        ).add_to(m)

    # Render map and capture viewport bounds
    map_data = st_folium(
        m,
        width=None,
        height=MAP_HEIGHT,
        returned_objects=['bounds'],
        key='college_map'
    )

    # Filter to visible viewport
    visible_df = filtered.copy()
    if map_data and map_data.get('bounds'):
        bounds = map_data['bounds']
        sw = bounds['_southWest']
        ne = bounds['_northEast']

        visible_df = filtered[
            (filtered['latitude'] >= sw['lat']) &
            (filtered['latitude'] <= ne['lat']) &
            (filtered['longitude'] >= sw['lng']) &
            (filtered['longitude'] <= ne['lng'])
        ]

        st.sidebar.write(f"Visible on map: {len(visible_df)} of {len(filtered)}")

    visible_df['ipeds'] = visible_df['college_id'].apply(lambda x: f"https://nces.ed.gov/collegenavigator/?id={x}")

    column_order = (
        "college_name",
        "distance",
        "city",
        "state",
        "outstate_tuition",
        "instate_tuition",
        "power6Low",
        "memberCount",
        "divisionName",
        "url",
        "ipeds",
        "books",
        "housing",
        "other_expenses",
        "total_outstate",
        "total_instate",
        "utr_id",
        "power6",
        "power6High",
        "college_id",
        "short_name",
        "latitude",
        "longitude",
    )

    st.dataframe(
        visible_df,
        use_container_width=True,
        height=table_height(),
        column_order=column_order,
        column_config={
            "distance": st.column_config.NumberColumn("Miles", format="%.0f"),
            "instate_tuition": st.column_config.NumberColumn("In State ($)"),
            "outstate_tuition": st.column_config.NumberColumn("Out of State ($)"),
            "power6Low": st.column_config.NumberColumn("Min UTR"),
            "divisionName": st.column_config.TextColumn("Division"),
            "books": st.column_config.NumberColumn("Books ($)"),
            "housing": st.column_config.NumberColumn("Housing ($)"),
            "other_expenses": st.column_config.NumberColumn("Other ($)"),
            "url": st.column_config.LinkColumn(
                "Website",
                width="small",
                display_text=r"open .com",
            ),
            "ipeds": st.column_config.LinkColumn(
                "IPEDS",
                width="small",
                display_text=r"open .gov",
            )
        }
    )

    st.markdown("""\
        <script defer data-domain="colleges.dataturd.com" src="https://plausible.dataturd.com/js/script.file-downloads.outbound-links.js"></script>
        """.strip(),
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
