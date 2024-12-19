import os
import pandas as pd
import streamlit as st
import pydeck as pdk

DATA_FILE = os.getenv('DATA_FILE', 'dist/utr_costs_df.pkl')

st.set_page_config(
    page_title="College Tennis Map",
    layout="wide"
)


@st.cache_data
def utr_cost_data():
    import pickle
    from io import StringIO

    with open(DATA_FILE, 'rb') as f:
        df = pickle.load(f)
        return pd.read_json(StringIO(df.to_json()))

def filter_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    side = st.sidebar
    min_utr = 0.0
    max_utr = df['power6Low'].max()
    utr_range = side.slider("UTR Filter", min_value=min_utr, max_value=max_utr, step=0.1, value=(min_utr, max_utr))

    min_outstate = df['total_outstate'].min()
    max_outstate = df['total_outstate'].max()
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

    return df

def main():
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
                    radius_scale=200,
                    elevation_scale=0,
                    pickable=True,
                    get_radius='radius'
                ),
            ],
            tooltip={"text": "{college_name}\nUTR: {power6Low}\n${total_outstate}"}, # type: ignore
        )
    )

    filtered['ipeds'] = filtered['college_id'].apply(lambda x: f"https://nces.ed.gov/collegenavigator/?id={x}")

    column_order = (
        "college_name",
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
        filtered,
        use_container_width=True,
        column_order=column_order,
        column_config={
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
