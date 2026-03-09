import sys
import os
import json
import io
import csv
from datetime import datetime
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent))

# Load env
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import pandas as pd

# ── Page config must be first Streamlit call ──────────────────────────────────
st.set_page_config(
    page_title="IOEC — Infosec Obligations Extractor",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
CATEGORIES = {
    "GOV":  "Governance & Risk",
    "IAM":  "Identity & Access Management",
    "LOG":  "Logging, Monitoring & Detection",
    "VULN": "Vulnerability & Patch Management",
    "SDLC": "Secure SDLC & Change Management",
    "IR":   "Incident Response",
    "DATA": "Data Security & Privacy",
    "TPRM": "Third-Party & Vendor Risk",
    "BCDR": "Business Continuity & Resilience",
    "PHYS": "Physical & Endpoint Security",
    "CUST": "Customer / Contractual Commitments",
    "PROD": "Product / Fraud-Specific Controls",
}

CATEGORY_LIST = list(CATEGORIES.keys())

CONFLICT_ICONS = {
    "high":   "🔴",
    "medium": "🟡",
    "low":    "🟢",
    "none":   "✅",
}

MODALITY_BADGES = {
    "must":     "🔴 must",
    "should":   "🟡 should",
    "may":      "🟢 may",
    "implicit": "⚪ implicit",
}

SET_TYPES = ["policies", "intranet", "contracts", "custom"]

# ── DB init ───────────────────────────────────────────────────────────────────
@st.cache_resource
def init_database():
    """Initialize DB once per app lifecycle."""
    try:
        from backend.db.session import init_db, SessionLocal
        init_db()
        return SessionLocal
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        return None


SessionLocal = init_database()


def get_db():
    """Get a DB session; caller is responsible for closing."""
    if SessionLocal is None:
        return None
    return SessionLocal()


# ── Session state helpers ─────────────────────────────────────────────────────
def ss_get(key, default=None):
    return st.session_state.get(key, default)


def ss_set(key, value):
    st.session_state[key] = value


# ── DB helpers ────────────────────────────────────────────────────────────────
def load_all_analyses():
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import Analysis
        return db.query(Analysis).order_by(Analysis.created_at.desc()).all()
    except Exception:
        return []
    finally:
        db.close()


def load_analysis(analysis_id: str):
    db = get_db()
    if db is None:
        return None
    try:
        from backend.db.models import Analysis
        return db.query(Analysis).filter(Analysis.id == analysis_id).first()
    except Exception:
        return None
    finally:
        db.close()


def load_documents(analysis_id: str):
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import Document
        return db.query(Document).filter(Document.analysis_id == analysis_id).order_by(Document.uploaded_at).all()
    except Exception:
        return []
    finally:
        db.close()


def load_obligations(analysis_id: str):
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import Obligation
        return db.query(Obligation).filter(Obligation.analysis_id == analysis_id).all()
    except Exception:
        return []
    finally:
        db.close()


def load_clusters(analysis_id: str):
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import Cluster
        return db.query(Cluster).filter(Cluster.analysis_id == analysis_id).order_by(Cluster.primary_category).all()
    except Exception:
        return []
    finally:
        db.close()


def load_cluster_members(cluster_id: str):
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import ClusterMember, Obligation
        members = db.query(ClusterMember).filter(ClusterMember.cluster_id == cluster_id).all()
        obligation_ids = [m.obligation_id for m in members]
        if not obligation_ids:
            return []
        return db.query(Obligation).filter(Obligation.id.in_(obligation_ids)).all()
    except Exception:
        return []
    finally:
        db.close()


def load_comparisons(analysis_a_id: str, analysis_b_id: str):
    db = get_db()
    if db is None:
        return None
    try:
        from backend.db.models import Comparison
        return db.query(Comparison).filter(
            ((Comparison.analysis_a_id == analysis_a_id) & (Comparison.analysis_b_id == analysis_b_id)) |
            ((Comparison.analysis_a_id == analysis_b_id) & (Comparison.analysis_b_id == analysis_a_id))
        ).order_by(Comparison.created_at.desc()).first()
    except Exception:
        return None
    finally:
        db.close()


def load_comparison_matches(comparison_id: str):
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import ComparisonMatch
        return db.query(ComparisonMatch).filter(ComparisonMatch.comparison_id == comparison_id).all()
    except Exception:
        return []
    finally:
        db.close()


def load_comparison_issues(comparison_id: str):
    db = get_db()
    if db is None:
        return []
    try:
        from backend.db.models import ComparisonIssue
        return db.query(ComparisonIssue).filter(ComparisonIssue.comparison_id == comparison_id).all()
    except Exception:
        return []
    finally:
        db.close()


def load_cluster_by_id(cluster_id: str):
    db = get_db()
    if db is None:
        return None
    try:
        from backend.db.models import Cluster
        return db.query(Cluster).filter(Cluster.id == cluster_id).first()
    except Exception:
        return None
    finally:
        db.close()


def count_docs(analysis_id: str) -> int:
    db = get_db()
    if db is None:
        return 0
    try:
        from backend.db.models import Document
        return db.query(Document).filter(Document.analysis_id == analysis_id).count()
    except Exception:
        return 0
    finally:
        db.close()


def count_obligations(analysis_id: str) -> int:
    db = get_db()
    if db is None:
        return 0
    try:
        from backend.db.models import Obligation
        return db.query(Obligation).filter(Obligation.analysis_id == analysis_id).count()
    except Exception:
        return 0
    finally:
        db.close()


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.title("🔐 IOEC")
        st.caption("Infosec Obligations Extractor & Comparator")
        st.divider()

        # API key status
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "****"
            st.success(f"API Key: `{masked}`")
        else:
            st.error("⚠️ ANTHROPIC_API_KEY not set")

        st.divider()
        st.subheader("Navigation")

        if st.button("🏠 Home", use_container_width=True,
                      type="primary" if ss_get("page") == "home" else "secondary"):
            ss_set("page", "home")
            ss_set("selected_analysis_id", None)
            st.rerun()

        # List analyses
        analyses = load_all_analyses()
        if analyses:
            st.caption("Analyses")
            for analysis in analyses:
                label = f"📋 {analysis.name}"
                is_selected = ss_get("selected_analysis_id") == analysis.id and ss_get("page") == "detail"
                if st.button(label, key=f"nav_{analysis.id}", use_container_width=True,
                             type="primary" if is_selected else "secondary"):
                    ss_set("page", "detail")
                    ss_set("selected_analysis_id", analysis.id)
                    st.rerun()

        st.divider()
        if st.button("🔍 Compare Analyses", use_container_width=True,
                     type="primary" if ss_get("page") == "compare" else "secondary"):
            ss_set("page", "compare")
            st.rerun()

        st.divider()
        st.caption(f"v1.0 · {datetime.now().strftime('%Y-%m-%d')}")


# ── Home page ─────────────────────────────────────────────────────────────────
def render_home():
    st.title("🔐 Infosec Obligations Extractor & Comparator")
    st.markdown(
        "Upload security policies, contracts, and intranet docs to automatically extract, "
        "cluster, and compare information security obligations using Claude AI."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Analyses", len(load_all_analyses()))
    total_obs = sum(count_obligations(a.id) for a in load_all_analyses())
    col2.metric("Total Obligations", total_obs)
    col3.metric("Categories", len(CATEGORIES))

    st.divider()

    # Create new analysis form
    with st.expander("➕ Create New Analysis", expanded=ss_get("show_create_form", False)):
        with st.form("create_analysis_form", clear_on_submit=True):
            name = st.text_input("Analysis Name *", placeholder="e.g., Q1 2026 Policy Review")
            set_type = st.selectbox("Document Set Type", SET_TYPES)
            notes = st.text_area("Notes (optional)", placeholder="Add context about this analysis...")
            submitted = st.form_submit_button("Create Analysis", type="primary")

            if submitted:
                if not name.strip():
                    st.error("Analysis name is required.")
                else:
                    db = get_db()
                    if db:
                        try:
                            from backend.services.analysis_service import create_analysis
                            analysis = create_analysis(db, name.strip(), set_type, notes.strip())
                            st.success(f"Analysis '{analysis.name}' created!")
                            ss_set("page", "detail")
                            ss_set("selected_analysis_id", analysis.id)
                            ss_set("show_create_form", False)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to create analysis: {e}")
                        finally:
                            db.close()

    st.divider()
    st.subheader("All Analyses")

    analyses = load_all_analyses()
    if not analyses:
        st.info("No analyses yet. Create one above to get started.")
        return

    # Build table data
    rows = []
    for a in analyses:
        doc_count = count_docs(a.id)
        obs_count = count_obligations(a.id)
        rows.append({
            "Name": a.name,
            "Type": a.set_type,
            "Created": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "—",
            "Docs": doc_count,
            "Obligations": obs_count,
            "ID": a.id,
        })

    df = pd.DataFrame(rows)

    # Header row
    header_cols = st.columns([3, 1, 2, 1, 1, 1])
    header_cols[0].markdown("**Name**")
    header_cols[1].markdown("**Type**")
    header_cols[2].markdown("**Created**")
    header_cols[3].markdown("**Docs**")
    header_cols[4].markdown("**Obligations**")
    header_cols[5].markdown("**Action**")

    for _, row in df.iterrows():
        cols = st.columns([3, 1, 2, 1, 1, 1])
        cols[0].write(row["Name"])
        cols[1].write(f"`{row['Type']}`")
        cols[2].write(row["Created"])
        cols[3].write(str(row["Docs"]))
        cols[4].write(str(row["Obligations"]))
        if cols[5].button("Open", key=f"open_{row['ID']}"):
            ss_set("page", "detail")
            ss_set("selected_analysis_id", row["ID"])
            st.rerun()


# ── Analysis Detail page ──────────────────────────────────────────────────────
def render_analysis_detail():
    analysis_id = ss_get("selected_analysis_id")
    if not analysis_id:
        st.warning("No analysis selected.")
        return

    analysis = load_analysis(analysis_id)
    if not analysis:
        st.error("Analysis not found.")
        return

    # Header
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title(f"📋 {analysis.name}")
        meta_parts = [f"Type: `{analysis.set_type}`", f"Taxonomy: `{analysis.taxonomy_version}`"]
        if analysis.created_at:
            meta_parts.append(f"Created: {analysis.created_at.strftime('%Y-%m-%d %H:%M')}")
        st.caption(" · ".join(meta_parts))
        if analysis.notes:
            st.info(analysis.notes)

    with col2:
        doc_count = count_docs(analysis_id)
        obs_count = count_obligations(analysis_id)
        st.metric("Documents", doc_count)
        st.metric("Obligations", obs_count)

    st.divider()

    tab_docs, tab_run = st.tabs(["📄 Documents", "🚀 Run & Results"])

    # ── Tab 1: Documents ──────────────────────────────────────────────────────
    with tab_docs:
        render_documents_tab(analysis)

    # ── Tab 2: Run & Results ──────────────────────────────────────────────────
    with tab_run:
        render_results_tab(analysis)


def render_documents_tab(analysis):
    st.subheader("Add Documents")

    input_method = st.radio(
        "Input method:",
        ["Upload File", "Paste Text", "Add URL"],
        horizontal=True,
        key=f"input_method_{analysis.id}",
    )

    if input_method == "Upload File":
        uploaded_file = st.file_uploader(
            "Upload PDF or DOCX",
            type=["pdf", "docx"],
            key=f"file_upload_{analysis.id}",
        )
        if uploaded_file:
            ext = Path(uploaded_file.name).suffix.lower().lstrip(".")
            source_type = "pdf" if ext == "pdf" else "docx"
            col1, col2 = st.columns([3, 1])
            col1.write(f"**{uploaded_file.name}** ({uploaded_file.size:,} bytes)")
            if col2.button("Add Document", key=f"add_file_{analysis.id}", type="primary"):
                db = get_db()
                if db:
                    try:
                        from backend.services.analysis_service import add_document_upload
                        file_bytes = uploaded_file.read()
                        doc = add_document_upload(db, analysis.id, uploaded_file.name, file_bytes, source_type)
                        st.success(f"Added: {doc.source_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add document: {e}")
                    finally:
                        db.close()

    elif input_method == "Paste Text":
        with st.form(f"paste_form_{analysis.id}", clear_on_submit=True):
            title = st.text_input("Title *", placeholder="e.g., Security Policy v2.1")
            text = st.text_area("Paste text content *", height=250,
                                placeholder="Paste your policy or document text here...")
            if st.form_submit_button("Add Pasted Text", type="primary"):
                if not title.strip() or not text.strip():
                    st.error("Title and text are required.")
                else:
                    db = get_db()
                    if db:
                        try:
                            from backend.services.analysis_service import add_document_paste
                            doc = add_document_paste(db, analysis.id, title.strip(), text.strip())
                            st.success(f"Added: {doc.source_name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add document: {e}")
                        finally:
                            db.close()

    elif input_method == "Add URL":
        with st.form(f"url_form_{analysis.id}", clear_on_submit=True):
            url = st.text_input("URL *", placeholder="https://example.com/security-policy")
            if st.form_submit_button("Add URL", type="primary"):
                if not url.strip() or not url.startswith("http"):
                    st.error("Please enter a valid URL starting with http.")
                else:
                    db = get_db()
                    if db:
                        try:
                            from backend.services.analysis_service import add_document_url
                            doc = add_document_url(db, analysis.id, url.strip())
                            st.success(f"Added URL: {doc.source_name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add URL: {e}")
                        finally:
                            db.close()

    st.divider()
    st.subheader("Document List")

    documents = load_documents(analysis.id)
    if not documents:
        st.info("No documents added yet. Add documents above.")
        return

    for doc in documents:
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 1, 2, 1])
            col1.write(f"**{doc.source_name}**")
            icon = {"pdf": "📄", "docx": "📝", "url": "🌐", "paste": "📋"}.get(doc.source_type, "📄")
            col2.write(f"{icon} `{doc.source_type}`")
            if doc.uploaded_at:
                col3.write(doc.uploaded_at.strftime("%Y-%m-%d %H:%M"))
            else:
                col3.write("—")
            if doc.source_url:
                col4.markdown(f"[Link]({doc.source_url})")


def render_results_tab(analysis):
    # Run controls
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        st.subheader("Run Analysis")

    with col2:
        use_clustering = st.checkbox("Enable clustering", value=True, key=f"use_cluster_{analysis.id}")

    doc_count = count_docs(analysis.id)
    obs_count = count_obligations(analysis.id)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.warning("⚠️ ANTHROPIC_API_KEY is not set. Set it in your .env file before running analysis.")
        return

    if doc_count == 0:
        st.info("Add at least one document in the Documents tab before running analysis.")
        return

    with col3:
        run_clicked = st.button(
            "▶️ Run Analysis",
            type="primary",
            key=f"run_btn_{analysis.id}",
            help=f"Process {doc_count} document(s) and extract obligations"
        )

    if run_clicked:
        with st.spinner(f"Running analysis on {doc_count} document(s)... This may take a few minutes."):
            db = get_db()
            if db:
                try:
                    from backend.services.analysis_service import run_analysis
                    result = run_analysis(db, analysis.id, use_clustering=use_clustering)
                    if "error" in result:
                        st.error(f"Analysis error: {result['error']}")
                    else:
                        st.success(
                            f"Analysis complete! Extracted {result.get('obligations_extracted', 0)} obligations "
                            f"from {result.get('documents_processed', 0)} document(s)."
                        )
                        st.rerun()
                except Exception as e:
                    st.error(f"Analysis failed: {e}")
                finally:
                    db.close()

    if obs_count == 0:
        st.info("No obligations extracted yet. Run the analysis above.")
        return

    st.divider()

    # Search/filter
    col1, col2 = st.columns([3, 1])
    with col1:
        search_query = st.text_input(
            "🔍 Search obligations",
            placeholder="Filter by keyword...",
            key=f"search_{analysis.id}",
        )
    with col2:
        modality_filter = st.selectbox(
            "Modality",
            ["All", "must", "should", "may", "implicit"],
            key=f"modality_filter_{analysis.id}",
        )

    # Export buttons
    obligations = load_obligations(analysis.id)
    clusters = load_clusters(analysis.id)

    ecol1, ecol2, _ = st.columns([1, 1, 4])
    with ecol1:
        if obligations:
            json_data = export_obligations_json(obligations)
            st.download_button(
                "⬇️ Export JSON",
                data=json_data,
                file_name=f"{analysis.name}_obligations.json",
                mime="application/json",
                key=f"export_json_{analysis.id}",
            )
    with ecol2:
        if obligations:
            csv_data = export_obligations_csv(obligations)
            st.download_button(
                "⬇️ Export CSV",
                data=csv_data,
                file_name=f"{analysis.name}_obligations.csv",
                mime="text/csv",
                key=f"export_csv_{analysis.id}",
            )

    st.divider()
    st.subheader("Results by Category")

    # Category tabs
    cat_tabs = st.tabs([f"{cat_id}: {CATEGORIES[cat_id]}" for cat_id in CATEGORY_LIST])

    for i, cat_id in enumerate(CATEGORY_LIST):
        with cat_tabs[i]:
            render_category_results(
                analysis.id, cat_id, clusters, obligations,
                search_query, modality_filter
            )


def render_category_results(analysis_id, cat_id, clusters, obligations, search_query, modality_filter):
    cat_clusters = [c for c in clusters if c.primary_category == cat_id]
    cat_obligations = [o for o in obligations if o.primary_category == cat_id]

    # Apply filters
    if search_query:
        q = search_query.lower()
        cat_obligations = [
            o for o in cat_obligations
            if q in o.normalized_statement.lower()
            or (o.quote_snippet and q in o.quote_snippet.lower())
        ]
        cat_clusters = [
            c for c in cat_clusters
            if q in c.representative_statement.lower()
        ]

    if modality_filter != "All":
        cat_obligations = [o for o in cat_obligations if o.modality == modality_filter]

    if not cat_obligations and not cat_clusters:
        st.caption(f"No obligations in {cat_id}.")
        return

    st.caption(
        f"**{CATEGORIES[cat_id]}** · "
        f"{len(cat_clusters)} cluster(s) · "
        f"{len(cat_obligations)} obligation(s)"
    )

    if cat_clusters:
        # Show clusters with members
        for cluster in cat_clusters:
            members = load_cluster_members(cluster.id)
            # Apply filters to members
            if search_query:
                q = search_query.lower()
                members = [m for m in members if q in m.normalized_statement.lower()]
            if modality_filter != "All":
                members = [m for m in members if m.modality == modality_filter]

            member_count = cluster.obligation_count
            with st.expander(
                f"**{cluster.representative_statement[:120]}{'...' if len(cluster.representative_statement) > 120 else ''}**  "
                f"— {member_count} obligation(s)",
                expanded=False
            ):
                st.markdown(f"*{cluster.representative_statement}*")
                st.divider()
                for obs in members:
                    render_obligation_row(obs)
    else:
        # No clusters, show obligations directly
        for obs in cat_obligations:
            render_obligation_row(obs)


def render_obligation_row(obs):
    """Render a single obligation with its metadata."""
    badge = MODALITY_BADGES.get(obs.modality, f"⚪ {obs.modality}")
    conf_pct = int(obs.confidence * 100)

    col1, col2, col3 = st.columns([5, 1, 1])
    with col1:
        st.markdown(f"{badge} &nbsp; {obs.normalized_statement}")
    with col2:
        st.caption(f"Conf: {conf_pct}%")
    with col3:
        # Source info
        try:
            locator = json.loads(obs.source_locator) if obs.source_locator else {}
        except Exception:
            locator = {}
        loc_parts = []
        if locator.get("page"):
            loc_parts.append(f"p.{locator['page']}")
        if locator.get("section"):
            loc_parts.append(str(locator["section"])[:20])
        st.caption(" · ".join(loc_parts) if loc_parts else "—")

    if obs.quote_snippet:
        st.caption(f"> _{obs.quote_snippet[:200]}_")

    # Detail pills
    details = []
    if obs.frequency_timing:
        details.append(f"🕒 {obs.frequency_timing}")
    if obs.owner_role:
        details.append(f"👤 {obs.owner_role}")
    if obs.scope_system:
        details.append(f"🖥️ {obs.scope_system}")
    if obs.retention_duration:
        details.append(f"📅 {obs.retention_duration}")
    if details:
        st.caption(" &nbsp;·&nbsp; ".join(details))

    try:
        secondary = json.loads(obs.secondary_categories) if obs.secondary_categories else []
    except Exception:
        secondary = []
    if secondary:
        st.caption(f"Also: {', '.join(secondary)}")

    st.divider()


# ── Export helpers ────────────────────────────────────────────────────────────
def export_obligations_json(obligations) -> str:
    data = []
    for obs in obligations:
        try:
            secondary = json.loads(obs.secondary_categories) if obs.secondary_categories else []
        except Exception:
            secondary = []
        try:
            locator = json.loads(obs.source_locator) if obs.source_locator else {}
        except Exception:
            locator = {}
        data.append({
            "id": obs.id,
            "primary_category": obs.primary_category,
            "secondary_categories": secondary,
            "normalized_statement": obs.normalized_statement,
            "modality": obs.modality,
            "action": obs.action,
            "object_field": obs.object_field,
            "scope_system": obs.scope_system,
            "frequency_timing": obs.frequency_timing,
            "retention_duration": obs.retention_duration,
            "owner_role": obs.owner_role,
            "evidence_hint": obs.evidence_hint,
            "quote_snippet": obs.quote_snippet,
            "source_locator": locator,
            "confidence": obs.confidence,
        })
    return json.dumps(data, indent=2)


def export_obligations_csv(obligations) -> str:
    output = io.StringIO()
    fieldnames = [
        "id", "primary_category", "secondary_categories",
        "normalized_statement", "modality", "action", "object_field",
        "scope_system", "frequency_timing", "retention_duration",
        "owner_role", "evidence_hint", "quote_snippet", "confidence",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for obs in obligations:
        try:
            secondary = json.loads(obs.secondary_categories) if obs.secondary_categories else []
        except Exception:
            secondary = []
        writer.writerow({
            "id": obs.id,
            "primary_category": obs.primary_category,
            "secondary_categories": ", ".join(secondary),
            "normalized_statement": obs.normalized_statement,
            "modality": obs.modality,
            "action": obs.action or "",
            "object_field": obs.object_field or "",
            "scope_system": obs.scope_system or "",
            "frequency_timing": obs.frequency_timing or "",
            "retention_duration": obs.retention_duration or "",
            "owner_role": obs.owner_role or "",
            "evidence_hint": obs.evidence_hint or "",
            "quote_snippet": obs.quote_snippet or "",
            "confidence": round(obs.confidence, 3),
        })
    return output.getvalue()


# ── Compare page ──────────────────────────────────────────────────────────────
def render_compare():
    st.title("🔍 Compare Analyses")
    st.markdown(
        "Select two analyses to compare their security obligations. "
        "The comparator will match similar clusters and identify conflicts, gaps, and alignment."
    )

    analyses = load_all_analyses()
    if len(analyses) < 2:
        st.warning("You need at least 2 analyses to run a comparison. Create more analyses first.")
        return

    analysis_names = {a.id: a.name for a in analyses}
    analysis_options = [(a.id, a.name) for a in analyses]

    col1, col2 = st.columns(2)
    with col1:
        analysis_a_label = st.selectbox(
            "Analysis A",
            options=[a_id for a_id, _ in analysis_options],
            format_func=lambda x: analysis_names[x],
            key="compare_a",
        )
    with col2:
        other_options = [a_id for a_id, _ in analysis_options if a_id != analysis_a_label]
        if not other_options:
            st.error("Please add more analyses.")
            return
        analysis_b_label = st.selectbox(
            "Analysis B",
            options=other_options,
            format_func=lambda x: analysis_names[x],
            key="compare_b",
        )

    # Check if both have obligations
    obs_a = count_obligations(analysis_a_label)
    obs_b = count_obligations(analysis_b_label)

    col1, col2, col3 = st.columns(3)
    col1.metric(f"{analysis_names[analysis_a_label]} obligations", obs_a)
    col2.metric(f"{analysis_names[analysis_b_label]} obligations", obs_b)

    if obs_a == 0 or obs_b == 0:
        st.warning("Both analyses must have obligations extracted before comparing. Run analysis on each first.")
        return

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.warning("⚠️ ANTHROPIC_API_KEY is not set.")
        return

    # Check for existing comparison
    existing = load_comparisons(analysis_a_label, analysis_b_label)

    if existing:
        matches = load_comparison_matches(existing.id)
        issues = load_comparison_issues(existing.id)
        col3.metric("Issues", len(issues))
        st.success(
            f"Existing comparison found (run {existing.created_at.strftime('%Y-%m-%d %H:%M')}): "
            f"{len(matches)} match(es), {len(issues)} issue(s)."
        )

    run_col, _ = st.columns([1, 3])
    if run_col.button("▶️ Run Comparison", type="primary"):
        with st.spinner("Running comparison... This may take a few minutes."):
            db = get_db()
            if db:
                try:
                    from backend.services.analysis_service import create_comparison
                    comparison = create_comparison(db, analysis_a_label, analysis_b_label)
                    st.success("Comparison complete!")
                    ss_set("current_comparison_id", comparison.id)
                    st.rerun()
                except Exception as e:
                    st.error(f"Comparison failed: {e}")
                finally:
                    db.close()

    if not existing:
        return

    st.divider()
    render_comparison_results(
        existing,
        analysis_names[analysis_a_label],
        analysis_names[analysis_b_label],
    )


def render_comparison_results(comparison, name_a: str, name_b: str):
    matches = load_comparison_matches(comparison.id)
    issues = load_comparison_issues(comparison.id)

    if not matches and not issues:
        st.info("No comparison results found. Run the comparison first.")
        return

    # Summary metrics
    total_issues = len(issues)
    pending_issues = sum(1 for i in issues if i.status == "pending")
    decided_issues = sum(1 for i in issues if i.status == "decided")

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Total Matches", len(matches))
    mcol2.metric("Total Issues", total_issues)
    mcol3.metric("Pending", pending_issues)
    mcol4.metric("Decided", decided_issues)

    # Conflict level breakdown
    conflict_counts = {}
    for m in matches:
        lvl = m.conflict_level or "none"
        conflict_counts[lvl] = conflict_counts.get(lvl, 0) + 1

    if conflict_counts:
        st.caption(
            " · ".join(
                f"{CONFLICT_ICONS.get(lvl, '')} {lvl}: {cnt}"
                for lvl, cnt in sorted(conflict_counts.items())
            )
        )

    tabs_list = ["📊 Category View", "⚠️ Issues Queue"]
    tab_cat, tab_issues = st.tabs(tabs_list)

    with tab_cat:
        render_comparison_by_category(comparison, matches, name_a, name_b)

    with tab_issues:
        render_issues_queue(comparison, issues, name_a, name_b)


def render_comparison_by_category(comparison, matches, name_a: str, name_b: str):
    # Group matches by category
    by_cat = {}
    for m in matches:
        cat = m.primary_category
        by_cat.setdefault(cat, []).append(m)

    present_cats = [c for c in CATEGORY_LIST if c in by_cat]
    if not present_cats:
        st.info("No category data available.")
        return

    cat_tab_labels = [f"{cat}: {CATEGORIES[cat]}" for cat in present_cats]
    cat_tabs = st.tabs(cat_tab_labels)

    for i, cat_id in enumerate(present_cats):
        with cat_tabs[i]:
            cat_matches = by_cat[cat_id]

            # Separate matched pairs, A-only, B-only
            paired = [m for m in cat_matches if m.cluster_a_id and m.cluster_b_id]
            a_only = [m for m in cat_matches if m.cluster_a_id and not m.cluster_b_id]
            b_only = [m for m in cat_matches if not m.cluster_a_id and m.cluster_b_id]

            st.caption(
                f"{len(paired)} matched pair(s) · "
                f"{len(a_only)} A-only · "
                f"{len(b_only)} B-only"
            )

            if paired:
                st.markdown("#### Matched Pairs")
                for m in paired:
                    cluster_a = load_cluster_by_id(m.cluster_a_id)
                    cluster_b = load_cluster_by_id(m.cluster_b_id)
                    conflict_icon = CONFLICT_ICONS.get(m.conflict_level or "none", "")
                    sim_pct = f"{int(m.similarity * 100)}%" if m.similarity is not None else "—"

                    with st.expander(
                        f"{conflict_icon} Similarity: {sim_pct} · Conflict: {m.conflict_level or 'none'}",
                        expanded=m.conflict_level in ("high", "medium")
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**{name_a}**")
                            if cluster_a:
                                st.info(cluster_a.representative_statement)
                                st.caption(f"Obligations: {cluster_a.obligation_count}")
                            else:
                                st.warning("Cluster not found")

                        with c2:
                            st.markdown(f"**{name_b}**")
                            if cluster_b:
                                st.info(cluster_b.representative_statement)
                                st.caption(f"Obligations: {cluster_b.obligation_count}")
                            else:
                                st.warning("Cluster not found")

                        # Diff details
                        if m.diff_json:
                            try:
                                diffs = json.loads(m.diff_json)
                                if diffs:
                                    st.markdown("**Differences:**")
                                    for d in diffs:
                                        sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                                            d.get("severity", "low"), ""
                                        )
                                        field = d.get("field", "")
                                        val_a = d.get("a", "—") or "—"
                                        val_b = d.get("b", "—") or "—"
                                        st.caption(f"{sev_icon} **{field}**: A=`{val_a}` → B=`{val_b}`")
                            except Exception:
                                pass

            if a_only:
                st.markdown(f"#### Only in {name_a}")
                for m in a_only:
                    cluster_a = load_cluster_by_id(m.cluster_a_id)
                    if cluster_a:
                        st.warning(f"🔴 {cluster_a.representative_statement}")

            if b_only:
                st.markdown(f"#### Only in {name_b}")
                for m in b_only:
                    cluster_b = load_cluster_by_id(m.cluster_b_id)
                    if cluster_b:
                        st.warning(f"🔴 {cluster_b.representative_statement}")


def render_issues_queue(comparison, issues, name_a: str, name_b: str):
    if not issues:
        st.success("No issues found — the two analyses are well-aligned!")
        return

    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        status_filter = st.selectbox(
            "Filter by status",
            ["All", "pending", "decided"],
            key=f"issue_status_{comparison.id}",
        )
    with col2:
        type_filter = st.selectbox(
            "Filter by type",
            ["All", "conflict", "missing_in_A", "missing_in_B"],
            key=f"issue_type_{comparison.id}",
        )

    filtered = issues
    if status_filter != "All":
        filtered = [i for i in filtered if i.status == status_filter]
    if type_filter != "All":
        filtered = [i for i in filtered if i.issue_type == type_filter]

    st.caption(f"Showing {len(filtered)} of {len(issues)} issue(s)")

    for issue in filtered:
        issue_icon = {
            "conflict":     "⚡",
            "missing_in_A": "➕",
            "missing_in_B": "➖",
        }.get(issue.issue_type, "❓")

        status_badge = "✅ Decided" if issue.status == "decided" else "⏳ Pending"
        cat_name = CATEGORIES.get(issue.primary_category, issue.primary_category)

        with st.expander(
            f"{issue_icon} [{issue.primary_category}] {issue.description[:100]}... — {status_badge}",
            expanded=(issue.status == "pending"),
        ):
            st.caption(f"Category: **{cat_name}** · Type: `{issue.issue_type}` · {status_badge}")
            st.markdown(f"**Description:** {issue.description}")

            # Proposed unified obligations
            if issue.proposed_unified_obligation:
                try:
                    proposals = json.loads(issue.proposed_unified_obligation)
                    if proposals:
                        st.markdown("**Proposed Unifications:**")
                        for key, val in proposals.items():
                            label_map = {
                                "strictest_merge": "Strictest Merge",
                                "align_to_a": f"Align to {name_a}",
                                "align_to_b": f"Align to {name_b}",
                            }
                            st.markdown(f"- **{label_map.get(key, key)}:** {val}")
                except Exception:
                    pass

            # Decision form
            if issue.status == "pending":
                with st.form(f"decision_{issue.id}"):
                    decision = st.radio(
                        "Decision:",
                        [
                            f"A is correct ({name_a})",
                            f"B is correct ({name_b})",
                            "Merge both",
                            "Needs further review",
                        ],
                        key=f"radio_{issue.id}",
                    )
                    notes = st.text_area(
                        "Notes (optional)",
                        key=f"notes_{issue.id}",
                        placeholder="Add context or rationale for this decision...",
                    )
                    if st.form_submit_button("Save Decision", type="primary"):
                        db = get_db()
                        if db:
                            try:
                                from backend.services.analysis_service import decide_issue
                                decide_issue(db, issue.id, decision, notes)
                                st.success("Decision saved.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to save decision: {e}")
                            finally:
                                db.close()
            else:
                # Show existing decision
                if issue.decision:
                    st.success(f"Decision: {issue.decision}")
                if issue.notes:
                    st.caption(f"Notes: {issue.notes}")


# ── Main app ──────────────────────────────────────────────────────────────────
def main():
    # Initialize session state
    if "page" not in st.session_state:
        st.session_state.page = "home"
    if "selected_analysis_id" not in st.session_state:
        st.session_state.selected_analysis_id = None

    render_sidebar()

    page = ss_get("page", "home")

    if page == "home":
        render_home()
    elif page == "detail":
        render_analysis_detail()
    elif page == "compare":
        render_compare()
    else:
        render_home()


if __name__ == "__main__" or True:
    main()
