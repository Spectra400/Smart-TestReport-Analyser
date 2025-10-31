# Streamlit_app.py
import streamlit as st
import tempfile
import pandas as pd
from analyzer import parse_xml_report, results_to_df

st.set_page_config(page_title="Smart Test Report Analyzer", layout="wide")

st.title("🛰️ Smart Test Report Analyzer")

uploaded = st.file_uploader("Upload an XML test report (JUnit, pytest, TestNG, custom)", type=["xml", "html"], accept_multiple_files=False)

def analyze_path(path):
    try:
        results = parse_xml_report(path)
        df = results_to_df(results)
        return df
    except Exception as e:
        st.error(f"Error parsing: {e}")
        return None

if uploaded is not None:
    # save to temp file (so parse_xml_report can read a file path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    st.info("Parsing file...")
    df = analyze_path(tmp_path)
    if df is None or df.empty:
        st.warning("No test cases detected.")
    else:
        # normalize status column
        if "status" in df.columns:
            df["status_norm"] = df["status"].str.upper().fillna("UNKNOWN")
        else:
            df["status_norm"] = "UNKNOWN"

        total = len(df)
        passed = int((df["status_norm"] == "PASS").sum())
        failed = int((df["status_norm"] == "FAIL").sum())
        skipped = int((df["status_norm"] == "SKIPPED").sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Tests", total)
        c2.metric("Passed", passed)
        c3.metric("Failed", failed)
        c4.metric("Skipped", skipped)

        st.markdown("### Test details")
        # show a compact table
        display_cols = [c for c in ["testcase", "classname", "time", "status_norm", "message"] if c in df.columns]
        st.dataframe(df[display_cols].rename(columns={"testcase":"Test","classname":"Class","time":"Time(s)","status_norm":"Status","message":"Message"}))

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "analysis.csv", "text/csv")
