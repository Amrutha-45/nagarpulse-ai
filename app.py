import json
import os
import uuid
from datetime import datetime
from typing import Literal

import pandas as pd
import pydeck as pdk
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------
# NagarPulse AI — hackathon MVP
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="NagarPulse AI | Civic Accountability",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOCALITIES = {
    "Madhapur": (17.4483, 78.3915),
    "Gachibowli": (17.4401, 78.3489),
    "Kukatpally": (17.4849, 78.4138),
    "Ameerpet": (17.4375, 78.4483),
    "Secunderabad": (17.4399, 78.4983),
    "Banjara Hills": (17.4126, 78.4482),
    "LB Nagar": (17.3457, 78.5522),
    "Uppal": (17.4058, 78.5591),
}

CATEGORIES = [
    "Roads & Potholes",
    "Water & Drainage",
    "Sanitation & Garbage",
    "Streetlights & Electrical",
    "Public Safety Hazard",
]
URGENCIES = ["Critical", "High", "Moderate", "Low"]
STATUSES = ["Reported", "In Progress", "Resolved"]

DEPARTMENT_BY_CATEGORY = {
    "Roads & Potholes": "GHMC Engineering Wing",
    "Water & Drainage": "HMWSSB Water Works / GHMC Drainage Wing",
    "Sanitation & Garbage": "GHMC Sanitation Department",
    "Streetlights & Electrical": "TGSPDCL Electrical / GHMC Street Lighting",
    "Public Safety Hazard": "GHMC Engineering Wing / Disaster Response",
}


class AnalysisResult(BaseModel):
    title: str = Field(description="A short 4 to 6 word headline.")
    category: Literal[
        "Roads & Potholes",
        "Water & Drainage",
        "Sanitation & Garbage",
        "Streetlights & Electrical",
        "Public Safety Hazard",
    ]
    severity_score: int = Field(ge=1, le=10)
    urgency: Literal["Critical", "High", "Moderate", "Low"]
    department: str
    hazard_reasoning: str = Field(description="One or two concise sentences about visible public risk.")
    formal_complaint: str = Field(description="Exactly three formal sentences addressed to the responsible department.")
    regional_summary_telugu: str = Field(description="Two simple sentences in Telugu script.")


def seed_tickets():
    """Illustrative demo records; not live GHMC complaints."""
    return [
        {
            "id": "NP-DEMO-001",
            "title": "Large Pothole Near Metro Road",
            "locality": "Madhapur",
            "lat": 17.4483, "lon": 78.3915,
            "category": "Roads & Potholes",
            "severity_score": 9, "urgency": "Critical",
            "department": "GHMC Engineering Wing",
            "hazard_reasoning": "The sample report describes a large road-surface defect that may cause two-wheelers to lose balance and may disrupt traffic.",
            "formal_complaint": "To the GHMC Engineering Wing, I request inspection of the reported road damage near Madhapur. The defect may create a safety risk for commuters and needs attention. Kindly inspect the location and update the repair status.",
            "regional_summary_telugu": "మాధాపూర్ ప్రాంతంలో రోడ్డుపై పెద్ద గుంత ఉన్నట్లు నివేదించారు. ప్రయాణికుల భద్రత కోసం దయచేసి పరిశీలించి మరమ్మతులు చేయండి.",
            "status": "Reported", "upvotes": 8, "created_at": "Demo record",
            "source": "Sample data",
        },
        {
            "id": "NP-DEMO-002",
            "title": "Water Leakage On Main Street",
            "locality": "Kukatpally",
            "lat": 17.4849, "lon": 78.4138,
            "category": "Water & Drainage",
            "severity_score": 7, "urgency": "High",
            "department": "HMWSSB Water Works / GHMC Drainage Wing",
            "hazard_reasoning": "The sample report describes water accumulating on a public street, which may affect pedestrians and nearby road users.",
            "formal_complaint": "To the concerned water and drainage department, I request an inspection of the reported water leakage in Kukatpally. Continued leakage may waste water and affect safe movement in the area. Kindly arrange an inspection and provide an update.",
            "regional_summary_telugu": "కూకట్‌పల్లిలో వీధిలో నీటి లీకేజీ ఉన్నట్లు నివేదించారు. నీటి వృథా మరియు ప్రజలకు ఇబ్బంది కలగకుండా దయచేసి పరిశీలించండి.",
            "status": "In Progress", "upvotes": 5, "created_at": "Demo record",
            "source": "Sample data",
        },
        {
            "id": "NP-DEMO-003",
            "title": "Garbage Accumulation Near Bus Stop",
            "locality": "Ameerpet",
            "lat": 17.4375, "lon": 78.4483,
            "category": "Sanitation & Garbage",
            "severity_score": 4, "urgency": "Moderate",
            "department": "GHMC Sanitation Department",
            "hazard_reasoning": "The sample report describes accumulated waste in a public area, which can cause odour and attract pests if left unattended.",
            "formal_complaint": "To the GHMC Sanitation Department, I request collection of the waste reported near the Ameerpet bus stop. The accumulation may affect cleanliness and public convenience. Kindly arrange cleaning and update the complaint status.",
            "regional_summary_telugu": "అమీర్‌పేట్ బస్‌స్టాప్ దగ్గర చెత్త పేరుకుపోయినట్లు నివేదించారు. పరిసరాల పరిశుభ్రత కోసం దయచేసి చెత్తను తొలగించండి.",
            "status": "Resolved", "upvotes": 12, "created_at": "Demo record",
            "source": "Sample data",
        },
    ]


def get_saved_api_key():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        return str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:
        return ""


def fallback_analysis(notes, category):
    """Offline demo fallback. It does not inspect the image."""
    dept = DEPARTMENT_BY_CATEGORY[category]
    if category == "Roads & Potholes":
        score, urgency = 7, "High"
        reason = "Offline demo mode: the selected category indicates a possible road-surface hazard. A field inspection is needed to confirm its size and actual risk."
        te = "ఈ ప్రాంతంలో రోడ్డు సమస్య ఉన్నట్లు నివేదించారు. ప్రయాణికుల భద్రత కోసం సంబంధిత అధికారులు పరిశీలించాలి."
    elif category == "Water & Drainage":
        score, urgency = 7, "High"
        reason = "Offline demo mode: the selected category may involve water leakage or drainage obstruction. The location should be checked to understand the extent of the issue."
        te = "ఈ ప్రాంతంలో నీరు లేదా డ్రైనేజీ సమస్య ఉన్నట్లు నివేదించారు. సమస్య తీవ్రతను అధికారులు పరిశీలించాలి."
    elif category == "Sanitation & Garbage":
        score, urgency = 4, "Moderate"
        reason = "Offline demo mode: the selected category indicates a possible sanitation concern. The amount of waste and its impact need on-site verification."
        te = "ఈ ప్రాంతంలో చెత్త సమస్య ఉన్నట్లు నివేదించారు. పరిశుభ్రత కోసం సంబంధిత సిబ్బంది పరిశీలించాలి."
    elif category == "Streetlights & Electrical":
        score, urgency = 6, "High"
        reason = "Offline demo mode: the selected category may involve a streetlight or electrical issue. The equipment should be checked by authorized personnel."
        te = "ఈ ప్రాంతంలో వీధి దీపం లేదా విద్యుత్ సమస్య ఉన్నట్లు నివేదించారు. సంబంధిత సిబ్బంది సురక్షితంగా పరిశీలించాలి."
    else:
        score, urgency = 8, "High"
        reason = "Offline demo mode: the selected category indicates a possible public safety concern. Keep a safe distance and request an authorized inspection."
        te = "ఈ ప్రాంతంలో ప్రజల భద్రతకు సంబంధించిన సమస్య ఉన్నట్లు నివేదించారు. దయచేసి సురక్షిత దూరంలో ఉండి అధికారులకు తెలియజేయండి."

    note_text = (notes or "").strip()
    title = {
        "Roads & Potholes": "Road Damage Reported By Citizen",
        "Water & Drainage": "Water Or Drainage Issue Reported",
        "Sanitation & Garbage": "Public Garbage Issue Reported",
        "Streetlights & Electrical": "Streetlight Or Electrical Issue",
        "Public Safety Hazard": "Public Safety Concern Reported",
    }[category]
    complaint = (
        f"To {dept}, I request an inspection of the reported {category.lower()} issue at the selected locality. "
        f"{'Citizen note: ' + note_text[:220] + '. ' if note_text else 'The issue may affect public convenience and safety. '}"
        "Kindly inspect the location and update the complaint status."
    )
    return {
        "title": title,
        "category": category,
        "severity_score": score,
        "urgency": urgency,
        "department": dept,
        "hazard_reasoning": reason,
        "formal_complaint": complaint,
        "regional_summary_telugu": te,
    }


def analyze_image_with_gemini(api_key, image_bytes, mime_type, locality, notes):
    client = genai.Client(api_key=api_key)
    prompt = f"""
You are a cautious civic-infrastructure triage assistant for Hyderabad, India.
Inspect the attached citizen photo and return only data matching the supplied JSON schema.
Locality selected by citizen: {locality}
Citizen notes (may be English, Telugu, or Hindi): {notes or "None provided"}

Rules:
- Describe only what is reasonably visible. Do not invent a precise address, cause, or official confirmation.
- Select exactly one allowed category.
- Severity is a triage estimate from 1 (minor) to 10 (immediate serious public hazard), not an official emergency assessment.
- Use these department mappings where appropriate:
  Roads & Potholes: GHMC Engineering Wing
  Water & Drainage: HMWSSB Water Works / GHMC Drainage Wing
  Sanitation & Garbage: GHMC Sanitation Department
  Streetlights & Electrical: TGSPDCL Electrical / GHMC Street Lighting
  Public Safety Hazard: GHMC Engineering Wing / Disaster Response
- Title must be 4 to 6 words.
- hazard_reasoning: 1-2 sentences.
- formal_complaint: exactly 3 sentences.
- regional_summary_telugu: exactly 2 simple sentences in Telugu script.
- If the photo is unclear or unrelated to civic infrastructure, say so in hazard_reasoning and use Low urgency with a conservative score.
"""
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, image_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnalysisResult,
            temperature=0.2,
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty response.")
    result = AnalysisResult.model_validate_json(response.text).model_dump()
    # Keep routing aligned with the app's department directory.
    result["department"] = DEPARTMENT_BY_CATEGORY[result["category"]]
    return result


def urgency_color(urgency):
    return {
        "Critical": [220, 38, 38, 190],
        "High": [234, 88, 12, 190],
        "Moderate": [202, 138, 4, 190],
        "Low": [22, 163, 74, 190],
    }.get(urgency, [100, 116, 139, 180])


def add_ticket(analysis, locality):
    lat, lon = LOCALITIES[locality]
    # Required hackathon MVP duplicate rule: same locality + category,
    # unresolved means Reported or In Progress.
    for existing in st.session_state.tickets:
        if (
            existing["locality"] == locality
            and existing["category"] == analysis["category"]
            and existing["status"] != "Resolved"
        ):
            existing["upvotes"] += 1
            return "duplicate", existing["id"]

    ticket = {
        "id": "NP-" + uuid.uuid4().hex[:7].upper(),
        "title": analysis["title"],
        "locality": locality,
        "lat": lat,
        "lon": lon,
        "category": analysis["category"],
        "severity_score": int(analysis["severity_score"]),
        "urgency": analysis["urgency"],
        "department": analysis["department"],
        "hazard_reasoning": analysis["hazard_reasoning"],
        "formal_complaint": analysis["formal_complaint"],
        "regional_summary_telugu": analysis["regional_summary_telugu"],
        "status": "Reported",
        "upvotes": 1,
        "created_at": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "source": "Citizen report",
    }
    st.session_state.tickets.insert(0, ticket)
    return "created", ticket["id"]


# --------------------------- State -----------------------------------
if "tickets" not in st.session_state:
    st.session_state.tickets = seed_tickets()
if "last_analysis" not in st.session_state:
    st.session_state.last_analysis = None
if "last_image_name" not in st.session_state:
    st.session_state.last_image_name = None

# --------------------------- Styling ---------------------------------
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px;}
      .hero {padding: 1.25rem 1.4rem; border-radius: 18px;
             background: linear-gradient(115deg, #102a43 0%, #176b87 55%, #2a9d8f 100%);
             color: white; margin-bottom: 1rem;}
      .hero h1 {color: white; margin: 0; font-size: 2.05rem;}
      .hero p {color: #e5f4f7; margin: .35rem 0 0 0;}
      .small-muted {color: #64748b; font-size: .86rem;}
      div[data-testid="stMetric"] {background: rgba(120,130,150,.08); padding: 12px 14px; border-radius: 12px;}
      .pill {display:inline-block; padding:3px 9px; border-radius:20px; font-size:12px; font-weight:600;}
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------- Sidebar ---------------------------------
with st.sidebar:
    st.title("🏙️ NagarPulse AI")
    st.caption("Civic grievance triage • Hyderabad demo")
    env_key = get_saved_api_key()
    if env_key:
        api_key = env_key
        st.success("Gemini API key loaded from environment / Streamlit secrets.")
    else:
        api_key = st.text_input(
            "Gemini API key (optional)",
            type="password",
            help="Used only for this session. Do not paste your key into a public GitHub file.",
        ).strip()
    st.divider()
    st.markdown("**Demo controls**")
    st.caption("The initial reports are illustrative sample records, not verified municipal complaints.")
    if st.button("↻ Reset sample dashboard", use_container_width=True):
        st.session_state.tickets = seed_tickets()
        st.session_state.last_analysis = None
        st.rerun()
    st.divider()
    st.caption("Privacy note: uploaded photos are processed in memory for analysis and are not saved by this MVP.")

# --------------------------- Header ----------------------------------
st.markdown(
    """
    <div class="hero">
      <h1>🏙️ NagarPulse AI</h1>
      <p>Civic problems. Visible action. AI-assisted reporting for Hyderabad.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tickets = st.session_state.tickets
total_reports = len(tickets)
critical_hazards = sum(
    1 for t in tickets if t["urgency"] == "Critical" and t["status"] != "Resolved"
)
resolved_issues = sum(1 for t in tickets if t["status"] == "Resolved")

m1, m2, m3 = st.columns(3)
m1.metric("Total Reports", total_reports, help="Includes illustrative sample reports.")
m2.metric("Critical Hazards", critical_hazards, help="Critical reports that are not resolved.")
m3.metric("Resolved Issues", resolved_issues)

tab_report, tab_dashboard, tab_officer = st.tabs(
    ["📝 Citizen Reporting", "🗺️ Public Dashboard", "🛠️ Officer Action Queue"]
)

# ======================= TAB 1: REPORTING ============================
with tab_report:
    st.subheader("Report a civic issue")
    st.write("Upload a photo, choose the locality, and let AI prepare a structured civic report.")
    left, right = st.columns([1, 1], gap="large")

    with left:
        uploaded = st.file_uploader(
            "Upload issue photo",
            type=["jpg", "jpeg", "png", "webp"],
            help="Use a clear photo of the civic issue. Avoid including faces, vehicle number plates, or private details.",
        )
        if uploaded:
            st.image(uploaded, caption=uploaded.name, use_container_width=True)
        locality = st.selectbox("Hyderabad locality", list(LOCALITIES.keys()))
        notes = st.text_area(
            "Citizen notes (optional)",
            placeholder="Describe what happened, nearby landmark, or how long the issue has existed. English, Telugu, or Hindi.",
            height=110,
        )
        fallback_category = st.selectbox(
            "Offline demo category",
            CATEGORIES,
            help="Used only if Gemini is unavailable or no API key is supplied.",
        )
        analyze_button = st.button(
            "✨ Analyze photo & prepare report",
            type="primary",
            use_container_width=True,
            disabled=uploaded is None,
        )

    with right:
        st.markdown("#### What the AI checks")
        st.markdown(
            "- Civic issue category and responsible department\n"
            "- Estimated public-safety severity (1–10)\n"
            "- Urgency level and short hazard reasoning\n"
            "- Three-sentence formal complaint draft\n"
            "- Two-sentence Telugu summary"
        )
        st.info(
            "AI triage is an assistive estimate, not an official inspection or emergency service. "
            "For immediate danger, contact the appropriate emergency service or municipal authority directly."
        )

    if analyze_button and uploaded is not None:
        image_bytes = uploaded.getvalue()
        mime_type = uploaded.type or "image/jpeg"
        if len(image_bytes) > 8 * 1024 * 1024:
            st.error("Please upload an image smaller than 8 MB.")
        else:
            with st.spinner("Reviewing the image and preparing a report..."):
                if api_key:
                    try:
                        result = analyze_image_with_gemini(
                            api_key, image_bytes, mime_type, locality, notes
                        )
                        st.session_state.last_analysis = {
                            **result,
                            "locality": locality,
                            "mode": "Gemini Vision",
                        }
                        st.session_state.last_image_name = uploaded.name
                    except Exception as exc:
                        result = fallback_analysis(notes, fallback_category)
                        st.session_state.last_analysis = {
                            **result,
                            "locality": locality,
                            "mode": "Offline fallback",
                            "api_error": str(exc)[:240],
                        }
                        st.session_state.last_image_name = uploaded.name
                else:
                    result = fallback_analysis(notes, fallback_category)
                    st.session_state.last_analysis = {
                        **result,
                        "locality": locality,
                        "mode": "Offline fallback",
                    }
                    st.session_state.last_image_name = uploaded.name

    analysis = st.session_state.last_analysis
    if analysis:
        st.divider()
        st.subheader("AI triage preview")
        if analysis.get("mode") == "Gemini Vision":
            st.success("Image analyzed with Gemini 2.5 Flash.")
        else:
            st.warning(
                "Offline fallback is active. The image was NOT analyzed by AI; "
                "the selected demo category and your notes were used instead."
            )
            if analysis.get("api_error"):
                with st.expander("Technical detail"):
                    st.code(analysis["api_error"])

        a1, a2, a3 = st.columns(3)
        a1.metric("Severity estimate", f'{analysis["severity_score"]}/10')
        a2.metric("Urgency", analysis["urgency"])
        a3.metric("Department", analysis["department"])
        st.markdown(f"### {analysis['title']}")
        st.write(f"**Category:** {analysis['category']}  ·  **Locality:** {analysis['locality']}")
        st.write("**Why it matters:**", analysis["hazard_reasoning"])
        with st.expander("Formal complaint draft", expanded=True):
            st.write(analysis["formal_complaint"])
        with st.expander("Telugu summary"):
            st.write(analysis["regional_summary_telugu"])

        if st.button("📣 Publish civic report", type="primary", use_container_width=True):
            outcome, ticket_id = add_ticket(analysis, analysis["locality"])
            if outcome == "duplicate":
                st.success(
                    f"Similar unresolved report found. Added your support to {ticket_id} instead of creating a duplicate."
                )
            else:
                st.success(f"Report published to the demo dashboard. Ticket ID: {ticket_id}")
            st.session_state.last_analysis = None
            st.rerun()

# ======================= TAB 2: DASHBOARD ============================
with tab_dashboard:
    st.subheader("Public accountability dashboard")
    st.caption("Illustrative demo data plus reports submitted during this app session.")
    f1, f2 = st.columns(2)
    status_filter = f1.selectbox("Filter by status", ["All"] + STATUSES, key="dash_status")
    category_filter = f2.selectbox("Filter by category", ["All"] + CATEGORIES, key="dash_category")

    filtered = [
        t for t in st.session_state.tickets
        if (status_filter == "All" or t["status"] == status_filter)
        and (category_filter == "All" or t["category"] == category_filter)
    ]

    st.markdown("#### Issue map")
    if filtered:
        map_df = pd.DataFrame(
            [
                {
                    "lat": t["lat"],
                    "lon": t["lon"],
                    "title": t["title"],
                    "locality": t["locality"],
                    "category": t["category"],
                    "status": t["status"],
                    "severity": t["severity_score"],
                    "color": urgency_color(t["urgency"]),
                }
                for t in filtered
            ]
        )
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_line_color=[255, 255, 255, 220],
            get_radius=150,
            radius_min_pixels=7,
            radius_max_pixels=18,
            pickable=True,
            stroked=True,
            filled=True,
        )
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(
                latitude=17.425, longitude=78.445, zoom=10, pitch=0
            ),
            tooltip={
                "html": "<b>{title}</b><br/>Locality: {locality}<br/>Category: {category}<br/>Status: {status}<br/>Severity: {severity}/10",
                "style": {"backgroundColor": "#102a43", "color": "white"},
            },
            map_style=None,
        )
        st.pydeck_chart(deck, use_container_width=True)
        st.caption("Pin coordinates are approximate locality-centre coordinates, not verified complaint addresses.")
    else:
        st.info("No reports match these filters.")

    st.markdown(f"#### Reports ({len(filtered)})")
    for ticket in sorted(filtered, key=lambda x: x["severity_score"], reverse=True):
        label = f'{ticket["title"]}  ·  {ticket["locality"]}  ·  {ticket["status"]}'
        with st.expander(
            f'{"🔴" if ticket["urgency"] == "Critical" else "🟠" if ticket["urgency"] == "High" else "🟡" if ticket["urgency"] == "Moderate" else "🟢"} {label}'
        ):
            c1, c2, c3 = st.columns(3)
            c1.metric("Severity", f'{ticket["severity_score"]}/10')
            c2.metric("Urgency", ticket["urgency"])
            c3.metric("Community support", ticket["upvotes"])
            st.write(f'**Ticket:** {ticket["id"]}')
            st.write(f'**Category:** {ticket["category"]}')
            st.write(f'**Department:** {ticket["department"]}')
            st.write(f'**AI / triage reasoning:** {ticket["hazard_reasoning"]}')
            st.write(f'**తెలుగు:** {ticket["regional_summary_telugu"]}')
            with st.expander("View formal complaint draft"):
                st.write(ticket["formal_complaint"])
            st.caption(f'Status: {ticket["status"]}  ·  Created: {ticket["created_at"]}  ·  Source: {ticket["source"]}')
            if st.button("🙋 Me Too / Upvote", key=f'upvote_{ticket["id"]}'):
                ticket["upvotes"] += 1
                st.rerun()

# ======================= TAB 3: OFFICER QUEUE ========================
with tab_officer:
    st.subheader("Municipal officer action queue")
    st.caption("Demo workflow only: status changes are visible in this app session; no municipal system is contacted.")
    queue = sorted(
        st.session_state.tickets,
        key=lambda x: (x["severity_score"], x["upvotes"]),
        reverse=True,
    )
    if not queue:
        st.info("No reports are currently in the queue.")
    for ticket in queue:
        with st.container(border=True):
            top1, top2 = st.columns([3, 1])
            top1.markdown(f'**{ticket["title"]}**')
            top1.caption(f'{ticket["id"]} · {ticket["locality"]} · {ticket["category"]}')
            top2.metric("Severity", f'{ticket["severity_score"]}/10')
            st.write(f'**Assigned department:** {ticket["department"]}')
            st.write(f'**Urgency:** {ticket["urgency"]}  ·  **Upvotes:** {ticket["upvotes"]}')
            current_index = STATUSES.index(ticket["status"])
            selected_status = st.selectbox(
                "Update report status",
                STATUSES,
                index=current_index,
                key=f'officer_status_{ticket["id"]}',
            )
            if selected_status != ticket["status"]:
                ticket["status"] = selected_status
                st.toast(f'{ticket["id"]} updated to {selected_status}')
                st.rerun()

st.divider()
st.caption(
    "NagarPulse AI is a student hackathon prototype. Sample records and approximate map pins are illustrative. "
    "It is not affiliated with GHMC, HMWSSB, TGSPDCL, or any government department."
)
