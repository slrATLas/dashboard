import streamlit as st
import subprocess

# Title for the combined app
st.title("Combined Streamlit App - Job Parser & Notion Uploader")

# Add a description
st.write("""
    This app first parses job descriptions and then uploads them to Notion.
    Press the button below to start each app sequentially.
""")

# Session state for tracking app progress
if 'app1_complete' not in st.session_state:
    st.session_state.app1_complete = False

# Run Job Parser (App 1)
if st.button('Run Job Parser (App 1)') and not st.session_state.app1_complete:
    st.write("Running Job Parser...")
    # Start App 1 (Job Parser)
    subprocess.run(["streamlit", "run", "app1_parser.py", "--server.port", "8501", "--server.headless", "true"])
    st.session_state.app1_complete = True
    st.write("Job Parser completed!")

# Run Notion Uploader (App 2) only after App 1 is complete
if st.session_state.app1_complete and st.button('Run Notion Uploader (App 2)'):
    st.write("Running Notion Uploader...")
    # Start App 2 (Notion Uploader)
    subprocess.run(["streamlit", "run", "app2_notion_uploader_v3.py", "--server.port", "8502", "--server.headless", "true"])
    st.write("Notion Uploader completed!")
