import streamlit as st
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
import os
import altair as alt

st.set_page_config(page_title="Medical Profile Dashboard", layout="wide")

try:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
except Exception as e:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

supabase = create_client(url, key)

@st.cache_data
def get_data():
    response = supabase.table('patients').select('*').execute()
    return pd.DataFrame(response.data)

df = get_data()
st.title("Patient Medical Profile Dashboard")
st.write("Contains demographic data, clinical observations, and computed BMI metrics from synthetic FHIR records.")

col1, col2, col3 = st.columns(3)
col1.metric("Total Ingested Patients", len(df))
col2.metric("Mean BMI", f"{df['bmi'].mean():.1f}" if 'bmi' in df and not df.empty else "N/A")
col3.metric("Gender Split (M : F)", f"{(df['gender'] == 'male').sum()} : {(df['gender'] == 'female').sum()}" if 'gender' in df and not df.empty else "N/A")

st.divider()

chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    st.subheader("Clinical BMI Categories")
    if 'bmi_category' in df and not df['bmi_category'].dropna().empty:
        bmi_order = ["Underweight", "Normal", "Overweight", "Obese"]
        
        counts = df['bmi_category'].value_counts().reindex(bmi_order, fill_value=0).reset_index()
        counts.columns = ['Category', 'Patients']
        
        # 2. Build Altair chart with an explicit categorical sort order
        chart = (
            alt.Chart(counts)
            .mark_bar()
            .encode(
                x=alt.X('Category:N', sort=bmi_order, axis=alt.Axis(labelAngle=0)),
                y=alt.Y('Patients:Q'),
                tooltip=['Category', 'Patients']
            )
            .properties(height=350)
        )
        
        st.altair_chart(chart, width='stretch')

with chart_col2:
    st.subheader("Gender Breakdown")
    if 'gender' in df and not df['gender'].empty:
        gender_counts = df['gender'].value_counts().reset_index()
        gender_counts.columns = ['Gender', 'Patients']
        
        gender_chart = (
            alt.Chart(gender_counts)
            .mark_bar()
            .encode(
                x=alt.X('Gender:N', axis=alt.Axis(labelAngle=0)),
                y=alt.Y('Patients:Q'),
                tooltip=['Gender', 'Patients']
            )
            .properties(height=350)
        )
        st.altair_chart(gender_chart, width='stretch')

st.divider()

st.subheader("Raw Ingested Clinical Records")

st.dataframe(df, width='stretch')