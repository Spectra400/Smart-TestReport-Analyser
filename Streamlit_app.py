# streamlit_app.py
import streamlit as st
import pandas as pd
import tempfile
import os
from analyzer import parse_xml_report, categorize_message
from io import StringIO

st.set_page_config(page_title="Smart Test Report Analyzer", layout="wide", initial_sidebar_state="collapsed")

# ---------- CSS ----------
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg,#071034 0%, #071434 100%); color: #e6eef8; }
    .card { background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.00)); padding:14px; border-radius:10px; box-shadow: 0 4px 18px rgba(2,6,23,0.6); }
    .hero-title { color:#eaf4ff; font-weight:800; font-size:26px; margin:0; }
    .hero-sub { color:#bcd7ff; margin-top:6px; }
    .small-muted { color:#9fb6e0; font-size:13px; }
    table.styled { border-collapse: collapse; width:100%; }
    table.styled th, table.styled td { padding:8px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.04); color:#e6eef8; }
    .cell-pass { background:#063f1a; color:#8ff1a1; font-weight:700; padding:6px; border-radius:6px; }
    .cell-fail { background:#3e0b0b; color:#ffb3b3; font-weight:700; padding:6px; border-radius:6px; }
    .cell-skipped { background:#3d3310; color:#ffd27a; font-weight:700; padding:6px; border-radius:6px; }
    .small-note { color:#9fb6e0; font-size:13px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Header with optional logo ----------
col1, col2 = st.columns([3,1])
with col1:
    st.markdown("<div class='hero-title'>🛰️ Smart Test Report Analyzer</div>", unsafe_allow_html=True)
    st.markdown("<div class='hero-sub'>Upload any XML test report — get instant insights, failure categories, and compare runs.</div>", unsafe_allow_html=True)
    st.markdown("<div class='small-muted'>Supports JUnit, PyTest, TestNG, NUnit and custom XML formats.</div>", unsafe_allow_html=True)
with col2:
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=120)
    else:
        st.markdown("<div class='small-note'>No logo found. Drop logo.png in project root to show here.</div>", unsafe_allow_html=True)

st.write("")  # spacer

# ---------- Main layout ----------
tab1, tab2 = st.tabs(["Analyze Single Report", "Compare Two Reports"])

# ------------- Helper utils -------------
def save_uploaded_to_tmp(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp:
        tmp.write(uploaded_file.read())
        return tmp.name

def df_from_results(results):
    df = pd.DataFrame(results)
    # normalize status to small words
    df["status_norm"] = df["status"].fillna("").astype(str).str.lower()
    df["status_norm"] = df["status_norm"].replace({
        "passed":"pass", "pass":"pass","ok":"pass",
        "failed":"fail","fail":"fail","error":"fail",
        "skipped":"skipped","skip":"skipped"
    }).fillna(df["status_norm"])
    df["category"] = (df["message"].fillna("") + " " + df["details"].fillna("")).apply(categorize_message)
    # ensure testcase and classname exist for merging
    df["testkey"] = df["testcase"].fillna("") + "||" + df["classname"].fillna("")
    return df

def html_table_from_df(df, show_cols=None, highlight_col="status_norm"):
    """Return HTML table string with colored status badges."""
    if show_cols is None:
        show_cols = df.columns.tolist()
    # build html
    rows = []
    # header
    header_cells = "".join([f"<th>{c}</th>" for c in show_cols])
    rows.append(f"<tr>{header_cells}</tr>")
    for _, r in df.iterrows():
        cells_html = ""
        for c in show_cols:
            val = r.get(c, "")
            if c == highlight_col:
                v = str(val).lower()
                if "pass" in v:
                    cells_html += f"<td><div class='cell-pass'>PASS</div></td>"
                elif "fail" in v:
                    cells_html += f"<td><div class='cell-fail'>FAIL</div></td>"
                elif "skip" in v or "skipped" in v:
                    cells_html += f"<td><div class='cell-skipped'>SKIPPED</div></td>"
                else:
                    cells_html += f"<td>{val}</td>"
            else:
                # escape basic html characters
                s = str(val).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                cells_html += f"<td>{s}</td>"
        rows.append(f"<tr>{cells_html}</tr>")
    table_html = f"<table class='styled'>\n{''.join(rows)}\n</table>"
    return table_html

# ------------- Tab 1: Single Report -------------
with tab1:
    st.markdown("<div class='card'><strong>Analyze Single XML Report</strong><div class='small-note'>Upload any XML test report to parse tests, categorize failures, and download analysis.</div></div>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload XML (single)", type=["xml"], key="single_uploader")
    if uploaded is not None:
        try:
            tmp_path = save_uploaded_to_tmp(uploaded)
            results = parse_xml_report(tmp_path)
            if not results:
                st.warning("No test cases detected in this XML.")
            else:
                df = df_from_results(results)
                total = len(df)
                passed = (df["status_norm"]=="pass").sum()
                failed = (df["status_norm"]=="fail").sum()
                skipped = (df["status_norm"]=="skipped").sum()
                pass_rate = round((passed/total)*100,1) if total else 0.0

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total Tests", total)
                c2.metric("Passed", int(passed), delta=f"{pass_rate}%")
                c3.metric("Failed", int(failed))
                c4.metric("Pass Rate", f"{pass_rate}%")

                st.progress(int(pass_rate))

                st.markdown("### Failure summary by category")
                summary = df[df["status_norm"]=="fail"].groupby("category").size().reset_index(name="count").sort_values("count", ascending=False)
                if not summary.empty:
                    st.dataframe(summary, use_container_width=True)
                else:
                    st.info("No failures found.")

                st.markdown("### Failed test details")
                failed_df = df[df["status_norm"]=="fail"].copy()
                if not failed_df.empty:
                    html = html_table_from_df(failed_df, show_cols=["testcase","classname","status_norm","category","message"], highlight_col="status_norm")
                    st.markdown(html, unsafe_allow_html=True)
                else:
                    st.success("No failed tests.")

                st.markdown("### All tests")
                html_all = html_table_from_df(df, show_cols=["testcase","classname","status_norm","category","message"], highlight_col="status_norm")
                st.markdown(html_all, unsafe_allow_html=True)

                # CSV download
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("Download analysis CSV", csv, "analysis_single.csv", "text/csv")
        except Exception as e:
            st.error(f"Error analyzing file: {e}")

# ------------- Tab 2: Compare Reports -------------
with tab2:
    st.markdown("<div class='card'><strong>Compare Two XML Reports</strong><div class='small-note'>Upload two XML reports (e.g., previous run and current run) to see new failures, fixed tests, and persistent failures.</div></div>", unsafe_allow_html=True)
    colA, colB = st.columns(2)
    with colA:
        uploaded_a = st.file_uploader("Upload Report A (older / baseline)", type=["xml"], key="compare_a")
    with colB:
        uploaded_b = st.file_uploader("Upload Report B (new / current)", type=["xml"], key="compare_b")

    if uploaded_a is not None and uploaded_b is not None:
        try:
            path_a = save_uploaded_to_tmp(uploaded_a)
            path_b = save_uploaded_to_tmp(uploaded_b)
            res_a = parse_xml_report(path_a)
            res_b = parse_xml_report(path_b)
            df_a = df_from_results(res_a)
            df_b = df_from_results(res_b)

            # merge on testkey (testcase||classname)
            merged = pd.merge(df_a, df_b, on="testkey", how="outer", suffixes=("_a","_b"))
            # fill missing names/class from either side
            merged["testcase"] = merged["testcase_a"].fillna(merged["testcase_b"])
            merged["classname"] = merged["classname_a"].fillna(merged["classname_b"])

            # status norm
            merged["status_a"] = merged["status_norm_a"].fillna("unknown")
            merged["status_b"] = merged["status_norm_b"].fillna("unknown")

            # categorize changes
            def change_type(row):
                a = row["status_a"]
                b = row["status_b"]
                if a!="fail" and b=="fail":
                    return "New Failure"
                if a=="fail" and b!="fail":
                    return "Fixed"
                if a=="fail" and b=="fail":
                    return "Persistent Failure"
                if a=="pass" and b=="pass":
                    return "Still Passing"
                return "Other/Changed"

            merged["change"] = merged.apply(change_type, axis=1)

            # summary counts
            new_fail = (merged["change"]=="New Failure").sum()
            fixed = (merged["change"]=="Fixed").sum()
            persistent = (merged["change"]=="Persistent Failure").sum()
            total_a = len(df_a)
            total_b = len(df_b)

            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Tests in A", total_a)
            s2.metric("Tests in B", total_b)
            s3.metric("New Failures", int(new_fail))
            s4.metric("Fixed", int(fixed))

            st.markdown("### New Failures (present in B but not failing in A)")
            new_fail_df = merged[merged["change"]=="New Failure"].copy()
            if not new_fail_df.empty:
                html_new = html_table_from_df(new_fail_df, show_cols=["testcase","classname","status_a","status_b","change","message_b"], highlight_col="status_b")
                st.markdown(html_new, unsafe_allow_html=True)
            else:
                st.info("No new failures")

            st.markdown("### Fixed (were failing in A, passing in B)")
            fixed_df = merged[merged["change"]=="Fixed"].copy()
            if not fixed_df.empty:
                html_fixed = html_table_from_df(fixed_df, show_cols=["testcase","classname","status_a","status_b","change","message_a","message_b"], highlight_col="status_b")
                st.markdown(html_fixed, unsafe_allow_html=True)
            else:
                st.info("No fixed tests")

            st.markdown("### Persistent Failures (failing in both A and B)")
            pers_df = merged[merged["change"]=="Persistent Failure"].copy()
            if not pers_df.empty:
                html_pers = html_table_from_df(pers_df, show_cols=["testcase","classname","status_a","status_b","change","message_b"], highlight_col="status_b")
                st.markdown(html_pers, unsafe_allow_html=True)
            else:
                st.info("No persistent failures")

            # Download comparison CSV
            out_csv = merged[["testcase","classname","status_a","status_b","change","message_a","message_b"]].to_csv(index=False).encode("utf-8")
            st.download_button("Download comparison CSV", out_csv, "comparison.csv", "text/csv")

        except Exception as e:
            st.error(f"Error comparing files: {e}")
