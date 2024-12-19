import pandas as pd
import streamlit as st
import duckdb
import pydeck as pdk
import json

st.set_page_config(layout="wide")

st.title("Colleges Map")
st.write(
    """This app accomodates the blog [here](<https://blog.streamlit.io/auto-generate-a-dataframe-filtering-ui-in-streamlit-with-filter_dataframe/>)
    and walks you through one example of how the Streamlit
    Data Science Team builds add-on functions to Streamlit.
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
    min_total_cost = df['total_cost'].min()
    max_total_cost = df['total_cost'].max()

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
    df['radius'] = df['total_cost'].apply(get_radius)

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

def utr_cost_data():
    con = duckdb.connect(':memory:')
    schools = pd.read_csv('data/hd2023.csv', encoding='latin1')
    charges = pd.read_csv('data/ic2023_ay.csv', encoding='latin1')
    costs = con.execute("""
    SELECT
        schools.unitid as college_id,
        trim(INSTNM) AS college_name,
        trim(IALIAS) AS short_name,
        city AS city,
        stabbr AS state,
        LATITUDE::float as latitude,
        LONGITUD::float as longitude,
        -- (try_cast(TUITION3 AS DECIMAL(10,2)) + try_cast(FEE3 as decimal(10,2)))::bigint AS total_cost,
        try_cast(CHG3AY3 AS DECIMAL(10,2)) AS total_cost
    FROM schools
    JOIN charges ON schools.UNITID = charges.UNITID
    """).fetchdf()

    costs.to_csv(path_or_buf='data/school_costs.csv', index=False)

    utr = utr_data()

    utr_costs = con.execute(r"""
    SELECT
        utr.*,
        costs.college_id,
        costs.total_cost
    FROM utr
    LEFT JOIN costs ON
       regexp_replace(utr.name, '\W', '', 'g') IN (regexp_replace(costs.college_name, '\W', '', 'g') )
    OR (length(costs.short_name) > 1 and regexp_replace(utr.shortName, '\W', '', 'g') IN (regexp_replace(costs.short_name, '\W', '', 'g') ))
    """).fetchdf()

    utr_costs.to_csv(path_or_buf='data/utr_costs.csv', index=False)

    # FIXME Strange bug if we don't convert from/to json
    return pd.read_json(utr_costs.to_json())


filtered = filter_dataframe(utr_cost_data())

map_center = [filtered['latLng'].apply(lambda x: x[0]).mean(), filtered['latLng'].apply(lambda x: x[1]).mean()]


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
                get_position=['latLng[1]', 'latLng[0]'],
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
        tooltip={"text": "{name}\nUTR: {power6Low}\n${total_cost}"}, # type: ignore
    )
)

st.dataframe(filtered)
