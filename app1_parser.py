import os
import re
import json
import streamlit as st
from openai import OpenAI
from markdownify import markdownify as md
from dotenv import load_dotenv

# =============================
# ENVIRONMENT SETUP
# =============================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    st.error("❌ Missing OPENAI_API_KEY in .env file.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =============================
# SMART JOB PARSER CLASS
# =============================
class SmartJobParser:
    def __init__(self):
        self.client = client

    # ---------- CLEAN TEXT ----------
    def clean_text(self, text):
        if not text:
            return ""
        replacements = {
            "–": "-", "—": "-", "•": "• ", "\xa0": " ", "\u2022": "• ",
            "\u2013": "-", "\u2014": "-"
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n{2,}", "\n\n", text)
        return text.strip()

    # ---------- FORMAT DETECTION ----------
    def detect_format(self, text):
        html_patterns = [r"<div", r"<p", r"<ul", r"<li", r"<br"]
        markdown_patterns = [r"#+\s", r"\*\*.+\*\*", r"\[.+\]\(.+\)"]
        if any(re.search(p, text, re.I) for p in html_patterns):
            return "html"
        elif any(re.search(p, text) for p in markdown_patterns):
            return "markdown"
        return "plain"

    # ---------- CONVERT TO MARKDOWN ----------
    def convert_to_markdown(self, text):
        fmt = self.detect_format(text)
        if fmt == "html":
            text = md(text, heading_style="ATX", bullets="•")
        mapping = {
            r"(?i)\b(job description|overview|summary)\b": "## Job Description",
            r"(?i)\b(responsibilities|duties|tasks)\b": "## Responsibilities",
            r"(?i)\b(qualifications|required skills|requirements)\b": "## Qualifications",
            r"(?i)\b(preferred|nice to have)\b": "## Preferred Qualifications",
            r"(?i)\b(education)\b": "## Education",
            r"(?i)\b(experience)\b": "## Experience",
            r"(?i)\b(salary|compensation|pay)\b": "## Compensation",
            r"(?i)\b(location|work location)\b": "## Location",
            r"(?i)\b(about us|company overview)\b": "## About Us",
            r"(?i)\b(benefits|perks|what we offer)\b": "## Benefits",
        }
        for p, rpl in mapping.items():
            text = re.sub(p, rpl, text)
        return text.strip()

    # ---------- HEURISTIC EXTRACTION ----------
    def heuristic_extract(self, text):
        info = {}
        salary = re.search(r"\$([0-9,]+)\s*-\s*\$?([0-9,]+)", text)
        if salary:
            info["salary_min"] = int(salary.group(1).replace(",", ""))
            info["salary_max"] = int(salary.group(2).replace(",", ""))
            info["currency"] = "USD"
        loc = re.search(r"([A-Z][a-z]+,\s*[A-Z]{2})", text)
        if loc:
            info["location"] = loc.group(1)
        visa = re.search(r"(?i)(no sponsorship|not offer sponsorship|OPT|CPT)", text)
        info["visa_sponsorship"] = not bool(visa)
        remote = re.search(r"(?i)(remote|hybrid|on-site)", text)
        if remote:
            info["remote_hybrid"] = remote.group(1).capitalize()
        return info

    # ---------- GPT-5 (with fallback to GPT-4o) ----------
    def parse_with_gpt5(self, markdown_text, heuristics):
        schema = {
            "position_title": "string",
            "company": "string",
            "location": {"regions": ["string"], "remote_hybrid": "string"},
            "salary": {"min": "number", "max": "number", "currency": "string"},
            "employment_type": "string",
            "responsibilities": ["string"],
            "required_qualifications": {
                "education": "string",
                "experience": "string",
                "core_skills": ["string"],
                "technical_tools": ["string"],
                "soft_skills": ["string"],
            },
            "preferred_qualifications": {"skills": ["string"], "experience": "string"},
            "application_deadline": "string",
            "start_date": "string",
            "visa_sponsorship": "boolean",
            "relocation_assistance": "boolean",
            "industry_keywords": ["string"],
        }

        system_msg = (
            "You are a precise AI parser. Extract structured job information "
            "and return a single valid JSON matching this schema:\n"
            + json.dumps(schema, indent=2)
        )

        user_msg = f"""
Heuristic pre-extracted info:
{json.dumps(heuristics, indent=2)}

Job Description (Markdown):
{markdown_text}
"""

        # Try GPT-5, then fallback to GPT-4o
        for model in ["gpt-5", "gpt-4o"]:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ],
                    response_format={"type": "json_object"},
                    max_completion_tokens=1500,
                )
                content = response.choices[0].message.content.strip()
                if not content:
                    continue
                parsed = json.loads(content)
                st.info(f"✅ Parsed using {model}")
                return parsed
            except Exception as e:
                st.warning(f"{model} failed: {e}")
                continue

        st.error("❌ No valid response from GPT models.")
        return {}

    # ---------- MAIN RUN ----------
    def run(self, jd_text):
        cleaned = self.clean_text(jd_text)
        md_text = self.convert_to_markdown(cleaned)
        heuristics = self.heuristic_extract(cleaned)
        parsed = self.parse_with_gpt5(md_text, heuristics)
        for k, v in heuristics.items():
            if k not in parsed or not parsed[k]:
                parsed[k] = v
        return parsed, md_text


# =============================
# STREAMLIT INTERFACE
# =============================
st.set_page_config(page_title="SmartCV Parser", layout="wide")
st.title("🧠 SmartCV — GPT-5 Job Parser (with GPT-4o fallback)")
st.caption("Parses job descriptions (any format) into structured JSON for SmartCV / Notion.")

parser = SmartJobParser()

tab1, tab2 = st.tabs(["📝 Paste JD", "📂 Upload .txt file"])

with tab1:
    jd_text = st.text_area("Paste job description", height=350)

with tab2:
    uploaded = st.file_uploader("Upload .txt file", type=["txt"])
    if uploaded:
        jd_text = uploaded.read().decode("utf-8")

if st.button("🔍 Parse with GPT-5"):
    if not jd_text.strip():
        st.error("Please provide a job description first.")
    else:
        with st.spinner("Parsing via GPT-5 / GPT-4o..."):
            result, md_text = parser.run(jd_text)

        st.subheader("🧩 Normalized Markdown")
        st.markdown(md_text)

        if result:
            st.success("✅ Parsed successfully!")
            st.json(result)
            with open("parsed_output.json", "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            st.info("💾 Saved as parsed_output.json")
        else:
            st.error("❌ No valid JSON extracted.")
