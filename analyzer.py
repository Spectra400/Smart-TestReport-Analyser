import pandas as pd
from bs4 import BeautifulSoup

def make_soup(content: str):
    """
    Create BeautifulSoup using the best available parser for the input.
    - If the content looks like XML (starts with <?xml or contains common test-report tags),
      prefer an XML parser ('lxml' if available, else 'xml').
    - Otherwise, try html5lib and fall back to html.parser.
    """
    preview = content.lstrip()[:200].lower()
    looks_like_xml = preview.startswith("<?xml") or ("<testsuite" in preview) or ("<testcase" in preview) or ("<testsuites" in preview)

    # If XML-like, try XML parsers first
    if looks_like_xml:
        for parser in ("lxml", "xml", "html.parser"):
            try:
                if parser in ("lxml", "xml"):
                    soup = BeautifulSoup(content, "xml")
                else:
                    soup = BeautifulSoup(content, parser)
                if soup is not None:
                    return soup
            except Exception:
                continue

    # Otherwise fallback to HTML parsing
    for parser in ("html5lib", "html.parser"):
        try:
            soup = BeautifulSoup(content, parser)
            if soup is not None:
                return soup
        except Exception:
            continue

    # Final fallback
    return BeautifulSoup(content, "html.parser")


def extract_test_results(xml_content: str):
    """
    Extract test case results from XML or HTML test reports (JUnit-style or similar).
    Returns a list of dictionaries (rows).
    """
    soup = make_soup(xml_content)
    rows = []

    # Common test case tags (for JUnit-like XML reports)
    for testcase in soup.find_all("testcase"):
        name = testcase.get("name", "Unnamed Test")
        classname = testcase.get("classname", "")
        time = testcase.get("time", "")

        # Determine status
        if testcase.find("failure") or testcase.find("error"):
            status = "Failed"
        elif testcase.find("skipped"):
            status = "Skipped"
        else:
            status = "Passed"

        # Extract message (if any)
        message = ""
        failure_tag = testcase.find(["failure", "error"])
        if failure_tag:
            message = failure_tag.get("message", "").strip() or failure_tag.text.strip()

        rows.append({
            "Test Name": name,
            "Class": classname,
            "Status": status,
            "Time (s)": time,
            "Message": message
        })

    # If still empty, maybe HTML-style report
    if not rows:
        tables = soup.find_all("table")
        for table in tables:
            headers = [th.text.strip() for th in table.find_all("th")]
            for tr in table.find_all("tr")[1:]:
                cells = [td.text.strip() for td in tr.find_all("td")]
                if len(cells) == len(headers) and headers:
                    row_dict = dict(zip(headers, cells))
                    rows.append(row_dict)

    return rows


def summarize_results(df: pd.DataFrame):
    """
    Summarize test results in a simple dictionary.
    """
    summary = {}
    if "Status" in df.columns:
        total = len(df)
        passed = len(df[df["Status"].str.lower() == "passed"])
        failed = len(df[df["Status"].str.lower() == "failed"])
        skipped = len(df[df["Status"].str.lower() == "skipped"])

        summary = {
            "Total Tests": total,
            "Passed": passed,
            "Failed": failed,
            "Skipped": skipped,
            "Pass Percentage": round((passed / total * 100), 2) if total > 0 else 0.0
        }

    return summary


def analyze_file(uploaded_file):
    """
    Main function to analyze uploaded test report files.
    Supports .xml, .html, and .htm formats.
    """
    try:
        content = uploaded_file.read().decode("utf-8", errors="ignore")
        results = extract_test_results(content)
        if not results:
            return None, "No valid test data found in the report."

        df = pd.DataFrame(results)
        summary = summarize_results(df)
        return (df, summary)

    except Exception as e:
        return None, f"Error while processing file: {e}"
