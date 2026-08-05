"""
Internal Training Survey Form — ABC-MIB Group Co., Ltd.

Streamlit + Supabase (Auth + Postgres) production app.
Run: streamlit run app.py
"""

import io
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ABC-MIB Training Survey",
    page_icon="📋",
    layout="centered",
    initial_sidebar_state="collapsed",
)

COMPANY_NAME = st.secrets.get("app", {}).get("company_name", "ABC-MIB Group Co., Ltd.")

RATING_OPTIONS = ["4 - Excellent", "3 - Good", "2 - Average", "1 - Poor"]
RATING_QUESTIONS = [
    ("q1_enjoyable", "1. I enjoyed the training session."),
    ("q2_organized", "2. The training was well organized."),
    ("q3_satisfied", "3. Overall, I am satisfied with this training."),
    ("q4_improved_understanding", "4. This training improved my understanding of the subject."),
    ("q5_respect_ideas", "5. My ideas and opinions were respected during the session."),
    ("q6_presenter_rating", "6. How would you rate the presenter?"),
]
OPEN_QUESTIONS = [
    ("q7_understanding_notes", "7. What did you understand from this training?"),
    ("q8_interesting_thing", "8. What was the most interesting thing you learned?"),
    ("q9_knowledge_application", "9. How will you apply this knowledge in your work?"),
    ("q10_challenge_addressed", "10. What challenge (if any) did this training help address?"),
    ("q11_future_topics", "11. What topics would you like to see in future training?"),
]

CUSTOM_CSS = """
<style>
    .block-container {max-width: 700px; padding-top: 2rem; padding-bottom: 3rem;}
    .survey-header {text-align: center; margin-bottom: 1.5rem;}
    .survey-header h1 {font-size: 1.4rem; margin-bottom: 0.1rem;}
    .survey-header h3 {font-size: 1.05rem; color: #555; font-weight: 400; margin-top: 0;}
    div[data-testid="stForm"] {border: 1px solid #e6e6e6; border-radius: 12px; padding: 1.5rem;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
# IMPORTANT: do NOT wrap this in @st.cache_resource. Streamlit Community
# Cloud runs one Python process shared by every visitor; a cached client
# would carry a single shared auth session and leak one user's login into
# another user's browser tab. Each browser session gets its own client,
# stored in that session's st.session_state.
def get_supabase() -> Client:
    if "sb_client" not in st.session_state:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        st.session_state.sb_client = create_client(url, key)
    return st.session_state.sb_client


# ---------------------------------------------------------------------------
# Session / auth helpers
# ---------------------------------------------------------------------------
def init_session_state():
    defaults = {
        "auth_user": None,      # {"id", "email"}
        "profile": None,        # row from users_profile
        "form_nonce": 0,        # bumped to reset the survey form widgets
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def load_profile(sb: Client, user_id: str):
    resp = sb.table("users_profile").select("*").eq("id", user_id).single().execute()
    return resp.data


def sign_in(sb: Client, email: str, password: str):
    result = sb.auth.sign_in_with_password({"email": email, "password": password})
    st.session_state.auth_user = {"id": result.user.id, "email": result.user.email}
    st.session_state.profile = load_profile(sb, result.user.id)


def sign_up(sb: Client, email: str, password: str, full_name: str, department: str, position: str):
    result = sb.auth.sign_up({"email": email, "password": password})
    if result.user is None:
        raise RuntimeError("Sign-up did not return a user. Please try again.")

    # If email confirmation is required, there is no active session yet.
    if result.session is not None and result.user.id:
        sb.table("users_profile").update(
            {"full_name": full_name, "department": department, "position": position}
        ).eq("id", result.user.id).execute()
        st.session_state.auth_user = {"id": result.user.id, "email": result.user.email}
        st.session_state.profile = load_profile(sb, result.user.id)
        return True  # logged in immediately
    return False  # needs email confirmation


def sign_out(sb: Client):
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    for k in ("auth_user", "profile", "sb_client"):
        st.session_state.pop(k, None)
    st.rerun()


# ---------------------------------------------------------------------------
# Auth screen
# ---------------------------------------------------------------------------
def render_auth_screen(sb: Client):
    st.markdown(
        f"""
        <div class="survey-header">
            <h1>{COMPANY_NAME}</h1>
            <h3>Internal Training Survey Form</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_tab, signup_tab = st.tabs(["Log In", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log In", use_container_width=True, type="primary")
        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                try:
                    sign_in(sb, email, password)
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

    with signup_tab:
        with st.form("signup_form"):
            full_name = st.text_input("Full Name", key="signup_name")
            col1, col2 = st.columns(2)
            with col1:
                department = st.text_input("Department", key="signup_dept")
            with col2:
                position = st.text_input("Position", key="signup_position")
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_password")
            password2 = st.text_input("Confirm Password", type="password", key="signup_password2")
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
        if submitted:
            if not all([full_name, email, password, password2]):
                st.error("Please fill in all required fields.")
            elif password != password2:
                st.error("Passwords do not match.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    logged_in = sign_up(sb, email, password, full_name, department, position)
                    if logged_in:
                        st.rerun()
                    else:
                        st.success("Account created! Please check your email to confirm, then log in.")
                except Exception as e:
                    st.error(f"Sign-up failed: {e}")


# ---------------------------------------------------------------------------
# Survey form (trainee)
# ---------------------------------------------------------------------------
def render_survey_form(sb: Client):
    profile = st.session_state.profile or {}

    st.markdown(
        f"""
        <div class="survey-header">
            <h1>{COMPANY_NAME}</h1>
            <h3>Internal Training Survey Form</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.write(f"Logged in as **{st.session_state.auth_user['email']}**")
        if st.button("Log Out", use_container_width=True):
            sign_out(sb)

    nonce = st.session_state.form_nonce

    with st.form(f"survey_form_{nonce}", clear_on_submit=False):
        st.subheader("Basic Information")

        trainee_name = st.text_input(
            "Trainee Name *", value=profile.get("full_name") or "", key=f"name_{nonce}"
        )
        c1, c2 = st.columns(2)
        with c1:
            position = st.text_input("Position", value=profile.get("position") or "", key=f"pos_{nonce}")
        with c2:
            department = st.text_input(
                "Department", value=profile.get("department") or "", key=f"dept_{nonce}"
            )

        training_course = st.text_input("Training Course *", key=f"course_{nonce}")
        presenter_name = st.text_input("Presenter Name", key=f"presenter_{nonce}")

        c3, c4 = st.columns(2)
        with c3:
            start_date = st.date_input("Start Date", value=date.today(), key=f"start_{nonce}")
        with c4:
            completed_date = st.date_input("Completed Date", value=date.today(), key=f"completed_{nonce}")

        c5, c6 = st.columns(2)
        with c5:
            training_hours = st.number_input(
                "Training Hours", min_value=0.0, step=0.5, key=f"hours_{nonce}"
            )
        with c6:
            time_range = st.text_input("Time Range (e.g. 09:00-12:00)", key=f"time_{nonce}")

        st.divider()
        st.subheader("Please rate the following")
        st.caption("4 = Excellent · 3 = Good · 2 = Average · 1 = Poor")

        rating_values = {}
        for field, label in RATING_QUESTIONS:
            st.markdown(f"**{label}** *")
            rating_values[field] = st.segmented_control(
                label, options=RATING_OPTIONS, key=f"{field}_{nonce}", label_visibility="collapsed"
            )

        st.divider()
        st.subheader("Your Feedback")

        open_values = {}
        for field, label in OPEN_QUESTIONS:
            open_values[field] = st.text_area(label, key=f"{field}_{nonce}", height=80)

        submitted = st.form_submit_button("Submit Survey", use_container_width=True, type="primary")

    if not submitted:
        return

    # ---- validation ----
    missing = []
    if not trainee_name.strip():
        missing.append("Trainee Name")
    if not training_course.strip():
        missing.append("Training Course")
    for field, label in RATING_QUESTIONS:
        if rating_values[field] is None:
            missing.append(label)

    if missing:
        st.error("Please complete the following required fields:\n\n- " + "\n- ".join(missing))
        return

    def rating_to_int(selected: str) -> int:
        return int(selected.split(" - ")[0])

    payload = {
        "user_id": st.session_state.auth_user["id"],
        "trainee_name": trainee_name.strip(),
        "position": position.strip(),
        "department": department.strip(),
        "training_course": training_course.strip(),
        "start_date": start_date.isoformat(),
        "completed_date": completed_date.isoformat(),
        "training_hours": training_hours,
        "time_range": time_range.strip(),
        "presenter_name": presenter_name.strip(),
        **{field: rating_to_int(rating_values[field]) for field, _ in RATING_QUESTIONS},
        **{field: open_values[field].strip() for field, _ in OPEN_QUESTIONS},
    }

    try:
        sb.table("survey_responses").insert(payload).execute()
        st.toast("Survey submitted — thank you!", icon="✅")
        st.session_state.form_nonce += 1  # forces a clean form on rerun
        st.rerun()
    except Exception as e:
        st.error(f"Could not submit survey: {e}")


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------
QUESTION_LABELS = {
    "q1_enjoyable": "Q1 Enjoyable",
    "q2_organized": "Q2 Organized",
    "q3_satisfied": "Q3 Satisfied",
    "q4_improved_understanding": "Q4 Understanding",
    "q5_respect_ideas": "Q5 Respect Ideas",
    "q6_presenter_rating": "Q6 Presenter",
}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_responses(_sb: Client, cache_key: str) -> pd.DataFrame:
    resp = _sb.table("survey_responses").select("*").order("created_at", desc=True).execute()
    df = pd.DataFrame(resp.data)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Responses")
    return output.getvalue()


def render_admin_dashboard(sb: Client):
    st.markdown(
        f"""
        <div class="survey-header">
            <h1>{COMPANY_NAME}</h1>
            <h3>Admin Analytics Dashboard</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.write(f"Logged in as **{st.session_state.auth_user['email']}** (admin)")
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        if st.button("Log Out", use_container_width=True):
            sign_out(sb)

    try:
        df = fetch_responses(sb, st.session_state.auth_user["id"])
    except Exception as e:
        st.error(f"Could not load responses: {e}")
        return

    if df.empty:
        st.info("No survey responses yet.")
        return

    # ---- Filters ----
    st.subheader("Filters")
    f1, f2, f3 = st.columns(3)
    with f1:
        courses = sorted(df["training_course"].dropna().unique().tolist())
        selected_courses = st.multiselect("Training Course", courses)
    with f2:
        departments = sorted(df["department"].dropna().unique().tolist())
        selected_departments = st.multiselect("Department", departments)
    with f3:
        min_date = df["created_at"].min().date()
        max_date = df["created_at"].max().date()
        date_range = st.date_input(
            "Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date
        )

    filtered = df.copy()
    if selected_courses:
        filtered = filtered[filtered["training_course"].isin(selected_courses)]
    if selected_departments:
        filtered = filtered[filtered["department"].isin(selected_departments)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_d, end_d = date_range
        filtered = filtered[
            (filtered["created_at"].dt.date >= start_d) & (filtered["created_at"].dt.date <= end_d)
        ]

    if filtered.empty:
        st.warning("No responses match the selected filters.")
        return

    rating_cols = list(QUESTION_LABELS.keys())
    filtered["overall_avg"] = filtered[rating_cols].mean(axis=1)

    # ---- Overview metrics ----
    st.subheader("Overview")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Submissions", len(filtered))
    m2.metric("Avg Overall Rating", f"{filtered['overall_avg'].mean():.2f} / 4")
    m3.metric("Courses Covered", filtered["training_course"].nunique())

    top_presenter_df = (
        filtered.dropna(subset=["presenter_name"])
        .groupby("presenter_name")["q6_presenter_rating"]
        .mean()
        .sort_values(ascending=False)
    )
    top_presenter = top_presenter_df.index[0] if not top_presenter_df.empty else "N/A"
    m4.metric("Top Rated Presenter", top_presenter)

    # ---- Average rating per course ----
    st.subheader("Average Rating by Course")
    course_avg = (
        filtered.groupby("training_course")["overall_avg"].mean().sort_values(ascending=False).round(2)
    )
    st.bar_chart(course_avg)

    # ---- Criteria ratings Q1-Q6 ----
    st.subheader("Average Rating by Criteria (Q1–Q6)")
    criteria_avg = filtered[rating_cols].mean().round(2)
    criteria_avg.index = [QUESTION_LABELS[c] for c in criteria_avg.index]
    st.bar_chart(criteria_avg)

    # ---- Top presenters table ----
    st.subheader("Top Rated Presenters")
    st.dataframe(
        top_presenter_df.round(2).reset_index().rename(
            columns={"presenter_name": "Presenter", "q6_presenter_rating": "Avg Rating"}
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ---- Data table ----
    st.subheader("All Submissions")
    display_cols = [
        "created_at", "trainee_name", "department", "training_course", "presenter_name",
        "overall_avg",
    ] + rating_cols + [f for f, _ in OPEN_QUESTIONS]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

    # ---- Export ----
    st.subheader("Export")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "Download CSV",
            data=filtered[display_cols].to_csv(index=False).encode("utf-8"),
            file_name=f"survey_responses_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with e2:
        st.download_button(
            "Download Excel (.xlsx)",
            data=to_excel_bytes(filtered[display_cols]),
            file_name=f"survey_responses_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    init_session_state()
    sb = get_supabase()

    if st.session_state.auth_user is None:
        render_auth_screen(sb)
        return

    if st.session_state.profile is None:
        try:
            st.session_state.profile = load_profile(sb, st.session_state.auth_user["id"])
        except Exception as e:
            st.error(f"Could not load your profile: {e}")
            if st.button("Log Out"):
                sign_out(sb)
            return

    role = (st.session_state.profile or {}).get("role", "user")
    if role == "admin":
        render_admin_dashboard(sb)
    else:
        render_survey_form(sb)


if __name__ == "__main__":
    main()
