import pandas as pd
import streamlit as st
import duckdb
import pydeck as pdk
import json

st.set_page_config(layout="wide")

st.title("Colleges Map")
st.write(
    """
    """
)

def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        _min = 0.0
        _max = 16.0
        utr_range = st.slider("UTR", min_value=_min, max_value=_max, step=0.1, value=(_min, _max))

    # Filter the DataFrame based on the UTR range
    df = df[df['power6Low'].between(*utr_range)]

    # Calculate minimum and maximum values for 'total_cost' in the filtered data
    min_total_cost = df['total_outstate'].min()
    max_total_cost = df['total_outstate'].max()

    def get_color(power6Low):
        normalized_value = (power6Low - utr_range[0]) / (utr_range[1] - utr_range[0])
        blue_component = int((1.0 - normalized_value) * 255)
        red_component = int(normalized_value * 255)
        return [red_component, 0, blue_component]

    def get_radius(total_cost):
        try:
            # Normalize total cost to the desired radius range (e.g., 5 to 50)
            normalized_value = (total_cost - min_total_cost) / (max_total_cost - min_total_cost)
            radius_range_min = 5
            radius_range_max = 50
            return int(normalized_value * (radius_range_max - radius_range_min) + radius_range_min)
        except Exception as e:
            return 5

    # Apply functions to create new columns 'color' and 'radius'
    df['color'] = df['power6Low'].apply(get_color)
    df['radius'] = df['total_outstate'].apply(get_radius)

    return df

def utr_data():
    data = json.loads(open('data/utr-mens.json').read())
    hits = pd.json_normalize(data['hits'])
    utr = pd.DataFrame()

    fields = [
        'id',
        'source.school.name',
        'source.school.shortName',
        'source.school.power6',
        'source.school.power6High',
        'source.school.power6Low',
        'source.school.conference.division.divisionName',
        'source.location.latLng',
        'source.location.cityName',
        'source.location.stateAbbr',
        'source.url',
        'source.memberCount',
    ]
    for field in fields:
        last_field = field.split('.')[-1]
        utr[last_field] = hits[field]

    return utr

@st.cache_data
def utr_cost_data():
    import pickle
    with open('data/utr_costs_df.pkl', 'rb') as f:
        df = pickle.load(f)
        return pd.read_json(df.to_json())

filtered = filter_dataframe(utr_cost_data())

map_center = [filtered['latitude'].mean(), filtered['longitude'].mean()]

st.pydeck_chart(
    pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=map_center[0],
            longitude=map_center[1],
            zoom=3,
            pitch=0
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=filtered,
                get_position=['longitude', 'latitude'],
                get_color='color',
                auto_highlight=True,
                radius_scale=300,
                radius_min_pixels=2,
                radius_max_pixels=150,
                elevation_scale=1,
                pickable=True,
                get_radius='radius'
            ),
        ],
        tooltip={"text": "{college_name}\nUTR: {power6Low}\n${total_outstate}"}, # type: ignore
    )
)

st.dataframe(filtered)
