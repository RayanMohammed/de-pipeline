import datetime
import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

TABLEAU_EMBED_URL = (
    "https://public.tableau.com/views/PatientCohortIndividualDashboards/"
    "CohortOverview?:showVizHome=no&:embed=true&:tabs=yes&:toolbar=yes"
)
TABLEAU_PUBLIC_LINK = (
    "https://public.tableau.com/views/PatientCohortIndividualDashboards/"
    "CohortOverview?:language=en-US&:display_count=n&:origin=viz_share_link"
)

st.set_page_config(page_title="Clinical Data Platform", layout="wide")

if "active_patient" not in st.session_state:
    # None until a lookup runs; once set: first_name/last_name/birth_date (what
    # was searched), found (bool), snapshot (PatientSnapshot dict or None),
    # and treat_as_new (the doctor explicitly said "different person" despite
    # a name+DOB match).
    st.session_state.active_patient = None


def compute_age(birth_date_str: str) -> int:
    bd = datetime.date.fromisoformat(birth_date_str)
    today = datetime.date.today()
    return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))


def fetch_patient_by_id(patient_id: str) -> dict | None:
    try:
        response = requests.get(f"{API_BASE_URL}/api/patients/{patient_id}", timeout=10)
    except requests.ConnectionError:
        st.error(f"Couldn't reach the API at {API_BASE_URL}.")
        return None
    return response.json() if response.status_code == 200 else None


def submit_visit(identity: dict, clinical: dict, force_new: bool) -> dict | None:
    """
    POST one visit to the manual-entry endpoint, render the outcome, and
    return the parsed response on success (or None on any failure) so the
    caller can decide how to refresh the on-screen patient state.
    """
    payload = {**identity, **clinical, "force_new": force_new}
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/patients/manual-entry", json=payload, timeout=10
        )
    except requests.ConnectionError:
        st.error(
            f"Couldn't reach the API at {API_BASE_URL}. "
            "Is `uvicorn api.main:app --reload` running?"
        )
        return None

    if response.status_code == 201:
        data = response.json()
        verb = "Updated existing" if data["matched_existing_patient"] else "Created new"
        st.success(
            f"{verb} patient record. BMI: {data['bmi']} ({data['bmi_category']}). "
            f"{data['observations_recorded']} observation(s) recorded."
        )
        return data
    elif response.status_code == 422:
        for err in response.json().get("detail", []):
            st.error(err.get("msg", "Validation error."))
    else:
        st.error(f"Unexpected error ({response.status_code}): {response.text}")
    return None


with st.sidebar:
    st.markdown("## Clinical Data Platform")
    view = st.radio(
        "View", ["Patient Chart", "Cohort Dashboards", "Recent Patients"],
        label_visibility="collapsed",
    )

st.title(view)


# Patient Chart: the primary, doctor-facing view: look a patient up, see
# who they are and their vitals trend, then chart today's visit against that
# context.
if view == "Patient Chart":
    st.caption(
        "Look up a patient by name and birth date to open their chart, "
        "or search for someone new to start one."
    )
    with st.form("patient_lookup_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            lookup_first = st.text_input("First name")
        with col2:
            lookup_last = st.text_input("Last name")
        with col3:
            lookup_dob = st.date_input(
                "Birth date",
                value=datetime.date(1990, 1, 1),
                min_value=datetime.date(1900, 1, 1),
                max_value=datetime.date.today(),
            )
        look_up_submitted = st.form_submit_button("Look Up")

    if look_up_submitted:
        if not lookup_first.strip() or not lookup_last.strip():
            st.warning("Enter a first and last name to look up a patient.")
        else:
            try:
                lookup_response = requests.get(
                    f"{API_BASE_URL}/api/patients/lookup",
                    params={
                        "first_name": lookup_first,
                        "last_name": lookup_last,
                        "birth_date": lookup_dob.isoformat(),
                    },
                    timeout=10,
                )
            except requests.ConnectionError:
                st.error(
                    f"Couldn't reach the API at {API_BASE_URL}. "
                    "Is `uvicorn api.main:app --reload` running?"
                )
            else:
                if lookup_response.status_code == 200:
                    data = lookup_response.json()
                    st.session_state.active_patient = {
                        "first_name": lookup_first.strip(),
                        "last_name": lookup_last.strip(),
                        "birth_date": lookup_dob.isoformat(),
                        "found": data["match_found"],
                        "snapshot": data["patient"],
                        "treat_as_new": False,
                    }
                else:
                    st.error(f"Unexpected error ({lookup_response.status_code}).")

    active = st.session_state.active_patient

    if active is None:
        st.info("Look up a patient above to open their chart.")
    else:
        st.divider()
        showing_existing = active["found"] and not active["treat_as_new"]

        if showing_existing:
            snap = active["snapshot"]
            age = compute_age(active["birth_date"])
            with st.container(border=True):
                st.markdown(f"#### {snap['first_name']} {snap['last_name']}")
                b1, b2, b3, b4 = st.columns(4)
                b1.metric("Age", age)
                b2.metric("Gender", (snap["gender"] or "—").title())
                bmi_display = (
                    f"{snap['bmi']} ({snap['bmi_category']})"
                    if snap["bmi"] is not None else "—"
                )
                b3.metric("Latest BMI", bmi_display)
                bp_display = (
                    f"{snap['latest_systolic_bp']}/{snap['latest_diastolic_bp']}"
                    if snap["latest_systolic_bp"] is not None else "—"
                )
                b4.metric("Latest BP", bp_display)
                if st.button("Not the same person — start a new chart instead"):
                    st.session_state.active_patient["treat_as_new"] = True
                    st.rerun()

            try:
                obs_response = requests.get(
                    f"{API_BASE_URL}/api/patients/{snap['id']}/observations", timeout=10
                )
            except requests.ConnectionError:
                obs_response = None

            if obs_response is not None and obs_response.status_code == 200:
                history = obs_response.json()
                if history:
                    hist_df = pd.DataFrame(history)
                    hist_df["observation_date"] = pd.to_datetime(hist_df["observation_date"])

                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        st.caption("Weight over time (kg)")
                        weight_df = hist_df[hist_df["observation_code"] == "29463-7"]
                        if not weight_df.empty:
                            st.line_chart(
                                weight_df.set_index("observation_date")["observation_value"]
                            )
                        else:
                            st.info("No weight history on file yet.")
                    with chart_col2:
                        st.caption("Blood pressure over time (mmHg)")
                        bp_df = hist_df[hist_df["observation_code"].isin(["8480-6", "8462-4"])]
                        if not bp_df.empty:
                            bp_pivot = bp_df.pivot_table(
                                index="observation_date",
                                columns="observation_description",
                                values="observation_value",
                            )
                            st.line_chart(bp_pivot)
                        else:
                            st.info("No blood pressure history on file yet.")
                else:
                    st.info("No observation history on file yet for this patient.")
        else:
            st.info(
                f"Starting a new chart for **{active['first_name']} {active['last_name']}** "
                f"(born {active['birth_date']})."
            )
            if active["found"] and active["treat_as_new"]:
                if st.button("Actually, that was the same person"):
                    st.session_state.active_patient["treat_as_new"] = False
                    st.rerun()

        st.markdown("##### Record a visit")
        gender_options = ["", "male", "female", "other"]
        default_gender = ""
        if showing_existing and active["snapshot"]["gender"] in gender_options:
            default_gender = active["snapshot"]["gender"]

        with st.form("visit_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                gender = st.selectbox(
                    "Gender", gender_options, index=gender_options.index(default_gender)
                )
                height_cm = st.number_input(
                    "Height (cm)", min_value=0.0, max_value=300.0, value=0.0, step=0.1
                )
                systolic_bp = st.number_input("Systolic BP", min_value=0, max_value=300, value=0)
            with col2:
                weight_kg = st.number_input(
                    "Weight (kg)", min_value=0.0, max_value=500.0, value=0.0, step=0.1
                )
                diastolic_bp = st.number_input("Diastolic BP", min_value=0, max_value=200, value=0)
            observation_date = st.date_input("Visit date", value=datetime.date.today())
            visit_submitted = st.form_submit_button("Record Visit")

        if visit_submitted:
            identity = {
                "first_name": active["first_name"],
                "last_name": active["last_name"],
                "birth_date": active["birth_date"],
            }
            clinical = {
                "gender": gender or None,
                "height_cm": height_cm if height_cm > 0 else None,
                "weight_kg": weight_kg if weight_kg > 0 else None,
                "systolic_bp": int(systolic_bp) if systolic_bp > 0 else None,
                "diastolic_bp": int(diastolic_bp) if diastolic_bp > 0 else None,
                "observation_date": observation_date.isoformat(),
            }
            force_new = active["found"] and active["treat_as_new"]
            result = submit_visit(identity, clinical, force_new)
            if result is not None:
                # Refresh by the exact patient id the write just returned,
                # never by re-running the name+DOB lookup.
                refreshed_snapshot = fetch_patient_by_id(result["patient_id"])
                st.session_state.active_patient = {
                    "first_name": active["first_name"],
                    "last_name": active["last_name"],
                    "birth_date": active["birth_date"],
                    "found": True,
                    "snapshot": refreshed_snapshot,
                    "treat_as_new": False,
                }
                st.rerun()


# Cohort Dashboards: the population-level Tableau embed.
elif view == "Cohort Dashboards":
    st.caption(
        "Live Tableau Public dashboards. Use the tabs inside the embedded "
        "view to switch between the cohort-level and per-patient dashboards."
    )
    left, center, right = st.columns([1, 10, 1])
    with center:
        with st.container(border=True):
            st.iframe(TABLEAU_EMBED_URL, height=850)
    st.markdown(f"[Open full dashboard in a new tab]({TABLEAU_PUBLIC_LINK})")


# Recent Patients: a sortable view of everyone on file.
elif view == "Recent Patients":
    st.caption("Live query against the patients table -- reflects new entries immediately.")
    if st.button("Refresh"):
        st.rerun()
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/patients",
            params={"limit": 100, "order_by": "created_at"},
            timeout=10,
        )
    except requests.ConnectionError:
        st.error(
            f"Couldn't reach the API at {API_BASE_URL}. "
            "Is `uvicorn api.main:app --reload` running?"
        )
    else:
        if response.status_code == 200:
            patients = response.json()
            if patients:
                df = pd.DataFrame(patients)
                avg_bmi = df["bmi"].dropna().mean()
                most_recent = pd.to_datetime(df["created_at"]).max()
                kpi1, kpi2, kpi3 = st.columns(3)
                kpi1.metric("Patients shown", len(df))
                kpi2.metric("Average BMI", f"{avg_bmi:.1f}" if pd.notna(avg_bmi) else "—")
                kpi3.metric("Most recent entry", most_recent.strftime("%b %d, %Y"))

                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "id": st.column_config.TextColumn("Patient ID", width="small"),
                        "first_name": "First Name",
                        "last_name": "Last Name",
                        "gender": "Gender",
                        "birth_date": st.column_config.DateColumn("Birth Date"),
                        "height_cm": st.column_config.NumberColumn("Height (cm)", format="%.1f"),
                        "weight_kg": st.column_config.NumberColumn("Weight (kg)", format="%.1f"),
                        "bmi": st.column_config.NumberColumn("BMI", format="%.1f"),
                        "bmi_category": "BMI Category",
                        "latest_systolic_bp": "Systolic BP",
                        "latest_diastolic_bp": "Diastolic BP",
                        "created_at": st.column_config.DatetimeColumn(
                            "Added", format="MMM D, YYYY h:mm a"
                        ),
                    },
                )
            else:
                st.info("No patients found.")
        else:
            st.error(f"Unexpected error ({response.status_code}): {response.text}")
