# =========================================
# 🧩 SmartCV — Module 2: Save Parsed Job to Notion
# =========================================
# Requires: streamlit, notion-client, python-dotenv, openai, requests
# =========================================

import os
import json
import hashlib
import datetime
import streamlit as st
import requests
from notion_client import Client
from dotenv import load_dotenv

# =========================================
# --- Environment and Setup
# =========================================

script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
st.info(f"Working directory set to: {script_dir}")

load_dotenv()
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
DB_JOBS = os.getenv("NOTION_DB_JOBS")
DB_ROLE_TEMPLATE = os.getenv("NOTION_DB_ROLE_TEMPLATE")
DB_COMPANIES = os.getenv("NOTION_DB_COMPANIES")

if not all([NOTION_API_KEY, DB_JOBS, DB_ROLE_TEMPLATE, DB_COMPANIES]):
    st.error("❌ Missing Notion variables in .env — check DB IDs and token.")
    st.stop()

notion = Client(auth=NOTION_API_KEY)

# =========================================
# --- Helper Functions
# =========================================

def hash_job_text(text, company):
    """Generate unique SHA256 hash for deduplication."""
    base = f"{company}_{text}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def notion_query(db_id, filter_obj):
    """Direct REST query (SDK-agnostic, works for all Notion versions)."""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    body = {"filter": filter_obj}
    res = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=headers, json=body)
    if res.status_code != 200:
        raise RuntimeError(f"❌ Notion query failed: {res.status_code} — {res.text}")
    return res.json()


def get_first_page_id(query_result):
    """Return first page ID from a Notion query result, or None if no match."""
    if not query_result or "results" not in query_result or not query_result["results"]:
        return None
    return query_result["results"][0]["id"]

# =========================================
# --- Builder Functions
# =========================================

def build_job_props(parsed, jd_text, source_url, job_hash):
    """Build JOBS database properties."""
    return {
        "Job Title": {"title": [{"text": {"content": parsed.get("position_title", "Untitled Job")}}]},
        "Company": {"rich_text": [{"text": {"content": parsed.get("company", "Unknown Company")}}]},
        "Job Description": {"rich_text": [{"text": {"content": jd_text[:1900]}}]},
        "Parsed Snapshot": {"rich_text": [{"text": {"content": json.dumps(parsed, ensure_ascii=False)[:1900]}}]},
        "Source URL": {"url": source_url or None},
        "Hash / Fingerprint": {"rich_text": [{"text": {"content": job_hash}}]},
        "Date Collected": {"date": {"start": datetime.datetime.utcnow().strftime("%Y-%m-%d")}},
        "Status": {"select": {"name": "Parsed"}},
    }


def build_role_props(parsed):
    """Build Role Template database properties."""
    skills = parsed.get("required_preferred_skills", {})
    return {
        "Role Title": {"title": [{"text": {"content": parsed.get("position_title", "Untitled Role")}}]},
        "Function": {"rich_text": [{"text": {"content": parsed.get("function", "")}}]},
        "Core Competencies": {"rich_text": [{"text": {"content": "\n• " + "\n• ".join(skills.get("core_competencies", []))}}]},
        "Responsibility": {"rich_text": [{"text": {"content": "\n• " + "\n• ".join(parsed.get("responsibilities", []))}}]},
        "Role Requirements": {"rich_text": [{"text": {"content": parsed.get("experience_level", "")}}]},
        "Technical Tools": {"rich_text": [{"text": {"content": "\n• " + "\n• ".join(skills.get("tools_technologies", []))}}]},
        "Industry ID": {"rich_text": [{"text": {"content": ", ".join(parsed.get("industry_keywords", []))}}]},
        "ATS Keywords": {"multi_select": [{"name": kw} for kw in parsed.get("ats_triggers", [])]},
        "Regions": {"multi_select": [{"name": r.replace(',', '')} for r in parsed.get("location", {}).get("regions", ["Global"])]},
        "Soft Skills": {"multi_select": [{"name": s} for s in skills.get("soft", [])]},
        "Target Companies": {"multi_select": [{"name": parsed.get("company", "Unknown Company")}]},
        "last_parsed_date": {"date": {"start": datetime.datetime.utcnow().isoformat()}},
        "parsed_json": {"rich_text": [{"text": {"content": json.dumps(parsed, ensure_ascii=False)[:1900]}}]},
    }


def build_company_props(parsed):
    """Build Company Catalog properties."""
    return {
        "Name": {"title": [{"text": {"content": parsed.get("company", "Unknown Company")}}]},
        "Industry": {"multi_select": [{"name": kw} for kw in parsed.get("industry_keywords", [])]},
        "Visa Policy": {"rich_text": [{"text": {"content": parsed.get("visa_citizenship_notes", "")}}]},
        "Culture / Values": {"rich_text": [{"text": {"content": parsed.get("culture", "")}}]},
        "Hiring Focus": {"rich_text": [{"text": {"content": parsed.get("company_focus", "")}}]},
        "Last Parsed Date": {"date": {"start": datetime.datetime.utcnow().isoformat()}},
        "parsed_json": {"rich_text": [{"text": {"content": json.dumps(parsed, ensure_ascii=False)[:1900]}}]},
    }

# =========================================
# --- Save Function
# =========================================

def save_to_notion(parsed, jd_text, source_url):
    """Main logic: deduplicate, save to JOBS, Role, and Company."""
    try:
        company = parsed.get("company", "Unknown Company")
        job_hash = hash_job_text(jd_text, company)

        # Deduplication
        q = notion_query(DB_JOBS, {"property": "Hash / Fingerprint", "rich_text": {"equals": job_hash}})
        if q.get("results"):
            st.warning("Warning: Duplicate detected. Job already exists in Notion.")
            return

        # Company
        q_company = notion_query(DB_COMPANIES, {"property": "Name", "title": {"contains": company[:60]}})
        company_props = build_company_props(parsed)
        company_page_id = get_first_page_id(q_company)
        if company_page_id:
            notion.pages.update(page_id=company_page_id, properties=company_props)
            st.info(f"🔁 Updated company record: {company}")
        else:
            new_company = notion.pages.create(parent={"database_id": DB_COMPANIES}, properties=company_props)
            company_page_id = new_company["id"]
            st.success(f"✅ Created new company record: {company}")

        # Role Template
        q_role = notion_query(DB_ROLE_TEMPLATE, {"property": "Role Title", "title": {"contains": parsed.get("position_title", "")[:60]}})
        role_props = build_role_props(parsed)
        role_props["Parsed Company"] = {"relation": [{"id": company_page_id}]}
        role_page_id = get_first_page_id(q_role)
        if role_page_id:
            notion.pages.update(page_id=role_page_id, properties=role_props)
            st.info(f"🔁 Updated role template: {parsed.get('position_title')}")
        else:
            new_role = notion.pages.create(parent={"database_id": DB_ROLE_TEMPLATE}, properties=role_props)
            role_page_id = new_role["id"]
            st.success(f"✅ Created new role template: {parsed.get('position_title')}")

        # JOB Entry
        job_props = build_job_props(parsed, jd_text, source_url, job_hash)
        job_props["Parsed Role Template"] = {"relation": [{"id": role_page_id}]}
        job_props["Parsed Company"] = {"relation": [{"id": company_page_id}]}

        new_job = notion.pages.create(parent={"database_id": DB_JOBS}, properties=job_props)
        st.success("🧠 Job successfully saved to Notion.")
        return new_job["id"]

    except Exception as e:
        st.error(f"❌ Save failed: {e}")
        raise

# =========================================
# --- Streamlit UI
# =========================================

st.set_page_config(page_title="SmartCV — Save to Notion", layout="wide")
st.title("🧠 SmartCV — Module 2: Save Parsed Job to Notion")
st.caption("Takes parsed JD from Module 1 and updates your Notion databases (JOBS, ROLE, COMPANY).")

parsed_json_path = os.path.join(script_dir, "parsed_output.json")
if os.path.exists(parsed_json_path):
    with open(parsed_json_path, "r", encoding="utf-8") as f:
        parsed = json.load(f)
    st.session_state["parsed_output"] = parsed
    st.session_state["markdown_output"] = parsed.get("markdown_text", "")
else:
    st.warning("⚠️ No parsed_output.json file found. Please run Module 1 first.")

if "parsed_output" not in st.session_state:
    st.warning("⚠️ No parsed job data found. Please run Module 1 first.")
else:
    parsed = st.session_state["parsed_output"]
    jd_text = st.session_state.get("markdown_output", "")
    st.subheader(f"🧩 Parsed Role: {parsed.get('position_title', 'Unknown Role')}")
    st.write(f"**Company:** {parsed.get('company', 'N/A')}")
    st.write(f"**Responsibilities Extracted:** {len(parsed.get('responsibilities', []))}")

    source_url = st.text_input("🔗 Source URL (optional)")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 Update Notion"):
            with st.spinner("Saving data to Notion..."):
                save_to_notion(parsed, jd_text, source_url)

    with col2:
        if st.button("🧹 Drop (Clear Session)"):
            st.session_state.clear()
            st.experimental_rerun()

    with col3:
        st.info("🧭 Parsed data will be linked automatically: JOB → ROLE → COMPANY.")
