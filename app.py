"""
SID-AI — Universal Engineering Drawing Intelligence Dashboard.

Supports any drawing type: P&ID, Electrical Layout, Earthing Layout,
SLD, HVAC, Structural, Cable Schedule, and Generic drawings.
The dashboard adapts its tabs and columns based on the detected drawing type.
"""
import os
import streamlit as st
import pandas as pd
from PIL import Image
from src.graph import create_workflow
from src.state import GraphState

# ─── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SID-AI | Universal Engineering Drawing Intelligence",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Premium Styling ───────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-title {
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
        font-weight: 400;
    }
    .metric-card {
        background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%);
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 5px solid #1a73e8;
        box-shadow: 0 2px 8px rgba(26,115,232,0.08);
        margin-bottom: 10px;
    }
    .metric-val {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1a1a2e;
    }
    .metric-lbl {
        font-size: 0.78rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
    }
    .dtype-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        color: white;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 12px;
    }
    .discipline-chip {
        display: inline-block;
        background: #e8f0fe;
        color: #1a73e8;
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1a1a2e;
        border-bottom: 2px solid #e8f0fe;
        padding-bottom: 8px;
        margin: 24px 0 16px 0;
    }
    .stDataFrame { border-radius: 8px; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ─── App Header ────────────────────────────────────────────────────────────────
st.markdown("<div class='main-title'>⚙️ SID-AI</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>Universal Engineering Drawing Intelligence — "
    "P&ID · Electrical · Earthing · SLD · HVAC · Structural · and more</div>",
    unsafe_allow_html=True,
)

# ─── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("## ⚙️ 2-Layer Extraction Pipeline")

max_retries = st.sidebar.slider(
    "Maximum Re-Extraction Cycles",
    min_value=0, max_value=5, value=3,
    help="Number of times the supervisor crops and re-scans suspect areas.",
)

st.sidebar.markdown("### 🔤 Layer 1: OCR Reading Layer")
ocr_option = st.sidebar.selectbox(
    "1st Layer: OCR Text Engine",
    options=[
        "PaddleOCR (Local / Offline)",
        "PyMuPDF Vector Text (Local / Offline)",
        "Gemini Vision OCR (Online API)",
        "Qwen 2.5-VL / Vision API (Online)",
    ],
    index=0,
    help="Select the 1st layer OCR engine. PaddleOCR & PyMuPDF run locally offline.",
)
ocr_engine_map = {
    "PaddleOCR (Local / Offline)": "paddle",
    "PyMuPDF Vector Text (Local / Offline)": "pdf_text",
    "Gemini Vision OCR (Online API)": "gemini_ocr",
    "Qwen 2.5-VL / Vision API (Online)": "qwen_ocr",
}
ocr_engine = ocr_engine_map.get(ocr_option, "paddle")

st.sidebar.markdown("### 🧠 Layer 2: Reasoning & Refinement Engine")
reasoning_option = st.sidebar.selectbox(
    "2nd Layer: Reasoning & Structuring",
    options=[
        "Rule-Based Regex Classifier (Local / Offline)",
        "Qwen 2.5 Reasoning Engine (OpenRouter / API)",
        "Gemini 2.0 Flash Engine (Online / API)",
        "OpenAI GPT-4o Engine (Online / API)",
    ],
    index=1,
    help="Select the 2nd layer reasoning engine. Online engines fix OCR typos, find missing tags, map misplaced data, and generate clean JSON.",
)
reasoning_engine_map = {
    "Rule-Based Regex Classifier (Local / Offline)": "rule_based",
    "Qwen 2.5 Reasoning Engine (OpenRouter / API)": "qwen",
    "Gemini 2.0 Flash Engine (Online / API)": "gemini",
    "OpenAI GPT-4o Engine (Online / API)": "openai",
}
reasoning_engine = reasoning_engine_map.get(reasoning_option, "qwen")

# Dynamic LLM Provider configuration for Qwen 2.5 (OpenRouter) / OpenAI / Custom Endpoints
llm_provider = "gemini"
llm_api_key = None
llm_base_url = None
llm_model = None

if reasoning_engine in ("qwen", "openai") or ocr_engine == "qwen_ocr":
    llm_provider = "qwen" if ("Qwen" in reasoning_option or ocr_engine == "qwen_ocr") else "openai"
    with st.sidebar.expander(f"🔧 {llm_provider.upper()} / OpenRouter Settings", expanded=True):
        default_key = os.getenv("OPENROUTER_API_KEY", os.getenv("QWEN_API_KEY", os.getenv("OPENAI_API_KEY", "")))
        llm_api_key = st.text_input(
            "API Key",
            value=default_key,
            type="password",
            help="OpenRouter API Key (sk-or-v1-...) or OpenAI / DashScope key.",
        )
        default_endpoint = os.getenv("QWEN_BASE_URL", "https://openrouter.ai/api/v1") if llm_provider == "qwen" else "https://api.openai.com/v1"
        llm_base_url = st.text_input(
            "Base URL / Endpoint",
            value=default_endpoint,
            help="Custom endpoint URL (e.g. OpenRouter https://openrouter.ai/api/v1, DashScope, or local Ollama/vLLM)",
        )
        default_model = os.getenv("QWEN_MODEL", "qwen/qwen-2.5-72b-instruct") if llm_provider == "qwen" else "gpt-4o"
        llm_model = st.text_input(
            "Model Name",
            value=default_model,
            help="Model identifier e.g. qwen/qwen-2.5-72b-instruct, qwen/qwen-2.5-coder-32b-instruct, qwen/qwen-2.5-vl-72b-instruct",
        )
elif reasoning_engine == "gemini":
    llm_provider = "gemini"
    llm_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

use_mocks = st.sidebar.checkbox(
    "Enable Demo Mock Fallbacks",
    value=False,
    help="Fall back to static mock data if rate limits or API errors occur.",
)

local_mode = st.sidebar.checkbox(
    "🔌 Force Full Offline Mode",
    value=False,
    help="Force local offline execution (PaddleOCR + Regex Classifier, zero API calls).",
)

if local_mode:
    st.sidebar.info("🔌 Full Offline Mode forced — PaddleOCR + Regex Classifier. Zero API tokens.")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Supported Drawing Types")
st.sidebar.markdown("""
- **P&ID** — Piping & Instrumentation
- **Electrical Layout** — Lighting / Power
- **Earthing Layout** — Grounding / Bonding
- **SLD** — Single Line Diagram
- **HVAC Layout** — Ventilation / Air Handling
- **Structural** — Civil / Framing Plans
- **Cable Schedule** — Cable Routing
- **Generic** — Any other drawing
""")

# ─── File Upload ───────────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>📂 Document Upload</div>", unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    uploaded_drawing = st.file_uploader(
        "Upload Engineering Drawing (PDF, PNG, JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        help="Upload any engineering drawing — P&ID, Electrical Layout, Earthing, SLD, HVAC, Structural, etc.",
    )

with col2:
    uploaded_refs = st.file_uploader(
        "Upload Legend Sheets or Reference Documents (Optional)",
        type=["pdf", "png", "jpg"],
        accept_multiple_files=True,
        help="Provide symbol legends, client coding standards, or specification sheets.",
    )

# ─── Run Button ────────────────────────────────────────────────────────────────
run_pipeline = st.button(
    "🚀 Run Extraction Pipeline",
    type="primary",
    disabled=(uploaded_drawing is None),
)

# ─── Pipeline Execution ────────────────────────────────────────────────────────
if run_pipeline and uploaded_drawing:
    temp_dir = os.path.join(os.getcwd(), "uploads")
    os.makedirs(temp_dir, exist_ok=True)

    drawing_path = os.path.join(temp_dir, uploaded_drawing.name)
    with open(drawing_path, "wb") as f:
        f.write(uploaded_drawing.read())

    ref_paths = []
    for ref in uploaded_refs:
        ref_path = os.path.join(temp_dir, ref.name)
        with open(ref_path, "wb") as f:
            f.write(ref.read())
        ref_paths.append(ref_path)

    raw_docs = [drawing_path] + ref_paths

    initial_state: GraphState = {
        "raw_documents": raw_docs,
        "metadata": {},
        "engineering_context": {},
        "extracted_entities": {
            "text_elements": [],
            "symbols": [],
            "relations": [],
            "geometry": {},
        },
        "engineering_graph": None,
        "validation_reports": [],
        "missing_entities": [],
        "revision_history": [],
        "deliverables": {},
        "re_extraction_count": 0,
        "max_re_extractions": max_retries,
        "ocr_engine": ocr_engine,
        "reasoning_engine": reasoning_engine,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_api_key": llm_api_key,
        "llm_base_url": llm_base_url,
        "use_mocks": use_mocks,
        "local_mode": local_mode or (reasoning_engine == "rule_based" and ocr_engine in ("paddle", "pdf_text")),
        "re_extracted_targets": [],
    }

    with st.spinner("🔍 Agent workflow running — ingesting, detecting drawing type, and extracting entities…"):
        try:
            workflow = create_workflow()
            app = workflow.compile()
            final_state = app.invoke(initial_state)
            st.session_state["pipeline_results"] = final_state
            st.success("✅ Pipeline Execution Completed Successfully!")
        except Exception as e:
            st.error(f"Pipeline execution error: {e}")
            import traceback
            st.code(traceback.format_exc())

# ─── Results Dashboard ─────────────────────────────────────────────────────────
if "pipeline_results" in st.session_state:
    state = st.session_state["pipeline_results"]
    metadata = state.get("metadata", {})
    graph = state.get("engineering_graph")
    reports = state.get("validation_reports", [])
    deliverables = state.get("deliverables", {})
    re_runs = state.get("re_extraction_count", 0)
    revision_history = state.get("revision_history", [])

    drawing_type = metadata.get("drawing_type", "GENERIC")
    discipline = metadata.get("discipline", "Unknown")

    # Drawing type badge
    from src.utils.drawing_type_detector import DRAWING_TYPE_LABELS, DrawingType
    try:
        dtype_enum = DrawingType(drawing_type)
        dtype_info = DRAWING_TYPE_LABELS.get(dtype_enum, {"label": drawing_type, "icon": "📋", "discipline": discipline})
    except Exception:
        dtype_info = {"label": drawing_type, "icon": "📋", "discipline": discipline}

    st.markdown(
        f"<div class='dtype-badge'>{dtype_info['icon']} {dtype_info['label']}"
        f"<span class='discipline-chip'>{discipline}</span></div>",
        unsafe_allow_html=True,
    )

    # ── Metadata Block ────────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📋 Drawing Metadata</div>", unsafe_allow_html=True)
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)

    with col_m1:
        st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Drawing Title</div><div class='metric-val'>{metadata.get('title', 'N/A')}</div></div>", unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Drawing Number</div><div class='metric-val'>{metadata.get('drawing_number', 'N/A')}</div></div>", unsafe_allow_html=True)
    with col_m3:
        st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Revision</div><div class='metric-val'>{metadata.get('revision', 'N/A')}</div></div>", unsafe_allow_html=True)
    with col_m4:
        st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Discipline</div><div class='metric-val'>{metadata.get('discipline', 'N/A')}</div></div>", unsafe_allow_html=True)
    with col_m5:
        st.markdown(f"<div class='metric-card'><div class='metric-lbl'>Client</div><div class='metric-val'>{metadata.get('client_name', 'N/A')}</div></div>", unsafe_allow_html=True)

    # ── Extracted Deliverables — Dynamic Tabs ─────────────────────────────────
    if graph:
        st.markdown("<div class='section-header'>📊 Extracted Data</div>", unsafe_allow_html=True)

        dt = drawing_type.upper()

        # ── P&ID / PFD / Isometric ─────────────────────────────────────────────
        if dt in ('PID', 'PFD', 'ISOMETRIC'):
            tab_line, tab_inst, tab_valve, tab_psv, tab_eq = st.tabs([
                f"📏 Line List ({len(graph.lines)})",
                f"🔵 Instrument List ({len(graph.instruments)})",
                f"🔧 Valve List ({len(graph.valves)})",
                f"🛡️ Safety Relief Valves ({len(graph.safety_relief_valves)})",
                f"⚙️ Equipment List ({len(graph.equipment)})",
            ])

            with tab_line:
                st.subheader("Line List (Piping Segments)")
                if graph.lines:
                    df = pd.DataFrame([l.model_dump() for l in graph.lines]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No piping lines detected.")

            with tab_inst:
                st.subheader("Instrument List")
                if graph.instruments:
                    df = pd.DataFrame([i.model_dump() for i in graph.instruments]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No instruments detected.")

            with tab_valve:
                st.subheader("Manual Valve List")
                if graph.valves:
                    df = pd.DataFrame([v.model_dump() for v in graph.valves]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No valves detected.")

            with tab_psv:
                st.subheader("Safety Relief Valve List")
                if graph.safety_relief_valves:
                    df = pd.DataFrame([p.model_dump() for p in graph.safety_relief_valves]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No safety relief valves detected.")

            with tab_eq:
                st.subheader("Equipment List")
                if graph.equipment:
                    df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No equipment detected.")

        # ── Electrical Layout ──────────────────────────────────────────────────
        elif dt == 'ELECTRICAL_LAYOUT':
            tab_lum, tab_panel, tab_cable, tab_eq, tab_ann = st.tabs([
                f"💡 Luminaires ({len(graph.luminaires)})",
                f"⚡ Distribution Boards ({len(graph.panels)})",
                f"🔌 Cables & Circuits ({len(graph.cables)})",
                f"⚙️ Equipment ({len(graph.equipment)})",
                f"📝 Annotations ({len(graph.annotations)})",
            ])

            with tab_lum:
                st.subheader("Luminaire / Lighting Fitting List")
                if graph.luminaires:
                    df = pd.DataFrame([l.model_dump() for l in graph.luminaires]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No luminaires detected.")

            with tab_panel:
                st.subheader("Distribution Boards & Panels")
                if graph.panels:
                    df = pd.DataFrame([p.model_dump() for p in graph.panels]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No panels/DBs detected.")

            with tab_cable:
                st.subheader("Cables & Circuits")
                if graph.cables:
                    df = pd.DataFrame([c.model_dump() for c in graph.cables]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No cables/circuits detected.")

            with tab_eq:
                st.subheader("Equipment List")
                if graph.equipment:
                    df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No equipment detected.")

            with tab_ann:
                st.subheader("Elevation Labels & Annotations")
                if graph.annotations:
                    df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No annotations detected.")

        # ── Earthing Layout ────────────────────────────────────────────────────
        elif dt == 'EARTHING_LAYOUT':
            tab_earth, tab_eq, tab_ann = st.tabs([
                f"⏚ Earthing Components ({len(graph.earthing_components)})",
                f"⚙️ Equipment / Structures ({len(graph.equipment)})",
                f"📝 Notes & Elevations ({len(graph.annotations)})",
            ])

            with tab_earth:
                st.subheader("Earthing Components (Bars, Pits, Conductors)")
                if graph.earthing_components:
                    df = pd.DataFrame([e.model_dump() for e in graph.earthing_components]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No earthing components detected.")

            with tab_eq:
                st.subheader("Earthed Equipment & Structures")
                if graph.equipment:
                    df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No equipment detected.")

            with tab_ann:
                st.subheader("Installation Notes & Elevation Labels")
                if graph.annotations:
                    df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No annotations detected.")

        # ── SLD ───────────────────────────────────────────────────────────────
        elif dt == 'SLD':
            tab_panel, tab_cable, tab_eq, tab_ann = st.tabs([
                f"🏗️ Switchgear & Panels ({len(graph.panels)})",
                f"🔌 Feeders & Breakers ({len(graph.cables)})",
                f"⚙️ Loads & Equipment ({len(graph.equipment)})",
                f"📝 Ratings & Notes ({len(graph.annotations)})",
            ])

            with tab_panel:
                st.subheader("Switchgear, Busbars & Panels")
                if graph.panels:
                    df = pd.DataFrame([p.model_dump() for p in graph.panels]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No panels detected.")

            with tab_cable:
                st.subheader("Feeders & Circuit Breakers")
                if graph.cables:
                    df = pd.DataFrame([c.model_dump() for c in graph.cables]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No feeders/breakers detected.")

            with tab_eq:
                st.subheader("Loads & Equipment")
                if graph.equipment:
                    df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No equipment detected.")

            with tab_ann:
                st.subheader("Ratings & Notes")
                if graph.annotations:
                    df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No annotations detected.")

        # ── Cable Schedule ─────────────────────────────────────────────────────
        elif dt == 'CABLE_SCHEDULE':
            tab_cable, tab_panel, tab_ann = st.tabs([
                f"🔌 Cable Schedule ({len(graph.cables)})",
                f"⚡ Panels ({len(graph.panels)})",
                f"📝 Notes ({len(graph.annotations)})",
            ])
            with tab_cable:
                if graph.cables:
                    df = pd.DataFrame([c.model_dump() for c in graph.cables]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No cables detected.")
            with tab_panel:
                if graph.panels:
                    df = pd.DataFrame([p.model_dump() for p in graph.panels]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No panels detected.")
            with tab_ann:
                if graph.annotations:
                    df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No annotations detected.")

        # ── HVAC / Structural / Generic ────────────────────────────────────────
        else:
            tab_eq, tab_generic, tab_ann = st.tabs([
                f"⚙️ Equipment ({len(graph.equipment)})",
                f"🔩 Components ({len(graph.generic_components)})",
                f"📝 Notes & Annotations ({len(graph.annotations)})",
            ])

            with tab_eq:
                st.subheader("Equipment List")
                if graph.equipment:
                    df = pd.DataFrame([e.model_dump() for e in graph.equipment]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No equipment detected.")

            with tab_generic:
                st.subheader("Detected Components")
                if graph.generic_components:
                    df = pd.DataFrame([g.model_dump() for g in graph.generic_components]).drop(columns=["coordinates"], errors="ignore")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No components detected.")

            with tab_ann:
                st.subheader("Annotations & Notes")
                if graph.annotations:
                    df = pd.DataFrame([a.model_dump() for a in graph.annotations])
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No annotations detected.")

        # ── Relationships ──────────────────────────────────────────────────────
        if graph.relationships:
            with st.expander(f"🔗 Engineering Relationships ({len(graph.relationships)})"):
                df = pd.DataFrame([r.model_dump() for r in graph.relationships])
                st.dataframe(df, use_container_width=True)

    # ── QA & Validation ───────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>🔍 Quality Assurance & Validation Logs</div>", unsafe_allow_html=True)
    col_v1, col_v2 = st.columns(2)

    with col_v1:
        st.subheader("Consistency Errors & Warnings")
        if reports:
            for r in reports:
                icon = "❌" if r["severity"] == "ERROR" else "⚠️"
                bg_color = "#FDF2F2" if r["severity"] == "ERROR" else "#FEFBF0"
                border_color = "#F05252" if r["severity"] == "ERROR" else "#FACA15"
                st.markdown(f"""
                <div style='background-color: {bg_color}; padding: 10px; border-left: 4px solid {border_color}; border-radius: 4px; margin-bottom: 8px;'>
                    <strong>{icon} {r.get('rule_id', 'RULE')} (Target: {r.get('target_tag', 'N/A')})</strong><br/>
                    <span style='font-size: 0.9rem;'>{r['message']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("✓ No validation discrepancies identified.")

    with col_v2:
        st.subheader("Extraction Process Log")
        st.markdown(f"**Re-extraction Loops:** `{re_runs}` / `{max_retries}`")
        st.markdown("**Revision History:**")
        for log in revision_history:
            action = log.get("action", str(log))
            st.markdown(f"- {action}")

    # ── Download Section ───────────────────────────────────────────────────────
    st.markdown("<div class='section-header'>📥 Export & Download</div>", unsafe_allow_html=True)
    st.markdown("Download deliverables formatted for standard engineering platforms:")

    col_d1, col_d2, col_d3, col_d4, col_d5 = st.columns(5)

    if deliverables:
        if "excel" in deliverables and os.path.exists(deliverables["excel"]):
            with open(deliverables["excel"], "rb") as f:
                col_d1.download_button(
                    "📊 Excel Deliverables",
                    data=f.read(),
                    file_name="engineering_deliverables.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        if "json_graph" in deliverables and os.path.exists(deliverables["json_graph"]):
            with open(deliverables["json_graph"], "rb") as f:
                col_d2.download_button(
                    "🕸️ JSON Graph",
                    data=f.read(),
                    file_name="master_graph.json",
                    mime="application/json",
                    use_container_width=True,
                )

        if "aveva_xml" in deliverables and os.path.exists(deliverables["aveva_xml"]):
            with open(deliverables["aveva_xml"], "rb") as f:
                col_d3.download_button(
                    "📐 AVEVA XML",
                    data=f.read(),
                    file_name="aveva_diagrams_export.xml",
                    mime="application/xml",
                    use_container_width=True,
                )

        if "comos_json" in deliverables and os.path.exists(deliverables["comos_json"]):
            with open(deliverables["comos_json"], "rb") as f:
                col_d4.download_button(
                    "🔧 COMOS JSON",
                    data=f.read(),
                    file_name="comos_hierarchy_export.json",
                    mime="application/json",
                    use_container_width=True,
                )

        if "sppid_csv" in deliverables and os.path.exists(deliverables["sppid_csv"]):
            with open(deliverables["sppid_csv"], "rb") as f:
                col_d5.download_button(
                    "🗃️ SmartPlant CSV",
                    data=f.read(),
                    file_name="sppid_import_tables.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
    else:
        st.info("No export files generated yet. Run the pipeline to generate deliverables.")
