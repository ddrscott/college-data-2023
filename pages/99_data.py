import streamlit as st
import pandas as pd

schools = pd.read_csv('data/hd2023.csv', encoding='latin1')
# schools['domain'] = schools['WEBADDR'].apply(parse_domain)

st.dataframe(schools)
