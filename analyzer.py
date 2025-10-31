# analyzer.py
"""
Smart Test Report Analyzer - robust multi-XML parser + aggressive fallback
Usage:
    python analyzer.py -i path/to/report.xml -o output_folder
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple
from collections import Counter, defaultdict
import pandas as pd

# Try importing BeautifulSoup
from bs4 import BeautifulSoup

# ---------------------------
# Categorization rules
# ---------------------------
CATEGORY_PATTERNS = [
    ("Timeout", [r"\btimeout\b", r"\btimed out\b", r"timeouterror"]),
    ("Element not found", [r"element not found", r"no such element", r"could not find element"]),
    ("Assertion", [r"assertionerror", r"\bassert\b", r"expected .* but", r"assert failed"]),
    ("Network/Connection", [r"connectionerror", r"failed to connect", r"connection refused", r"socket.timeout"]),
    ("Database", [r"\bdb\b", r"\bdatabase\b", r"sqlexception", r"postgres", r"mysql", r"sqlite"]),
    ("Auth/Authorization", [r"unauthorized", r"\bauth\b", r"403", r"401", r"forbidden"]),
    ("Performance", [r"\bslow\b", r"response time", r"timed out after"]),
]

def categorize_message(msg: str) -> str:
    text = (msg or "").lower()
    for cat, patterns in CATEGORY_PATTERNS:
        for p in patterns:
            try:
                if re.search(p, text):
                    return cat
            except re.error:
                continue
    return "Other"

# ---------------------------
# Parser fallback
# ---------------------------
def make_soup(content: str):
    """
    Create BeautifulSoup using best available parser.
    Tries: lxml -> html5lib -> xml -> html.parser
    """
    parsers_to_try = ["lxml", "html5lib", "xml", "html.parser"]
    for parser in parsers_to_try:
        try:
            soup = BeautifulSoup(content, parser)
            if soup is not None:
                return soup
        except Exception:
            continue
    # last fallback
    return BeautifulSoup(content, "html.parser")

# ---------------------------
# Heuristics & helpers
# ---------------------------
TEST_TAG_HINTS = {
    "testcase", "test-case", "test", "testresult", "unittestresult"
}
FAILURE_CHILD_TAGS = {"failure", "error", "failed", "reason", "failuremessage", "failure-message"}

def is_test_tag(tag_name: str) -> bool:
    if not tag_name:
        return False
    name = tag_name.lower()
    if name in TEST_TAG_HINTS:
        return True
    if re.search(r"(test|case|result|unittest|test-case)", name):
        return True
    return False

def extract_text(node) -> str:
    if node is None:
        return ""
    for attr in ("message", "reason", "text", "failureMessage", "failure-message"):
        if node.has_attr(attr):
            return str(node.get(attr)).strip()
    return (node.text or "").strip()

def get_status_and_message(node) -> Tuple[str, str, str]:
    """
    Return (status, message, details) for a node that represents a test (best-effort).
    """
    # attributes indicating status
    for attr in ("result", "outcome", "status"):
        if node.has_attr(attr):
            val = node.get(attr).strip().lower()
            if val in ("failed", "fail", "error", "failure"):
                msg = extract_text(node)
                details = node.text or ""
                return "FAIL", msg, (details or "").strip()
            if val in ("passed", "pass", "ok", "success"):
                return "PASS", "", ""
            if val in ("skipped", "ignored", "skip"):
                return "SKIPPED", "", ""
    # direct child failure tags
    for child in node.find_all(recursive=False):
        cname = (child.name or "").lower()
        if cname in FAILURE_CHILD_TAGS:
            msg = extract_text(child) or extract_text(node)
            details = child.text or node.text or ""
            return "FAIL", msg.strip(), (details or "").strip()
    # descendant failure tags
    for tagname in FAILURE_CHILD_TAGS:
        found = node.find(tagname)
        if found:
            msg = extract_text(found) or extract_text(node)
            details = found.text or node.text or ""
            return "FAIL", msg.strip(), (details or "").strip()
    # attribute message
    for attr in ("message", "reason", "failure"):
        if node.has_attr(attr):
            val = node.get(attr)
            return "FAIL", str(val).strip(), (node.text or "").strip()
    # text heuristics
    txt = (node.text or "").lower()
    if "traceback" in txt or "assertionerror" in txt or "error:" in txt:
        firstline = txt.splitlines()[0] if txt.strip() else ""
        return "FAIL", firstline.strip(), txt.strip()
    # default pass
    return "PASS", "", ""

# ---------------------------
# Find test nodes and extract info
# ---------------------------
def find_test_nodes(soup) -> List:
    candidates = []
    # common <testcase> tags
    candidates.extend(soup.find_all("testcase"))
    # tags with name-like attributes or test hints
    for tag in soup.find_all():
        name_attr = tag.get("name") or tag.get("testName") or tag.get("testname") or tag.get("method") or tag.get("test")
        if name_attr:
            if is_test_tag(tag.name) or re.search(r"(test|case|result)", (tag.name or "").lower()):
                candidates.append(tag)
                continue
        if tag.has_attr("outcome") and tag.has_attr("testname"):
            candidates.append(tag)
            continue
        if tag.has_attr("result") and (tag.has_attr("name") or tag.has_attr("testname")):
            candidates.append(tag)
    # Deduplicate preserving order
    seen = set()
    uniq = []
    for c in candidates:
        ident = (c.name, str(c.get("name") or c.get("testname") or c.get("method") or c.get("id") or ""), id(c))
        if ident not in seen:
            uniq.append(c)
            seen.add(ident)
    return uniq

def get_test_info(node) -> Dict:
    name = node.get("name") or node.get("testName") or node.get("testname") or node.get("method") or node.get("id") or ""
    classname = node.get("classname") or node.get("class") or node.get("className") or ""
    time = node.get("time") or node.get("duration") or ""
    status, message, details = get_status_and_message(node)
    if not name:
        name_tag = node.find("name")
        if name_tag and (name_tag.text or "").strip():
            name = name_tag.text.strip()
    return {
        "testcase": str(name).strip(),
        "classname": str(classname).strip(),
        "time": str(time).strip(),
        "status": status,
        "message": (message or "").strip(),
        "details": (details or "").strip()
    }

# ---------------------------
# Inference fallbacks
# ---------------------------
def infer_tests_from_repeated_siblings(soup) -> List:
    results = []
    root = soup.find()  # first tag
    if root is None:
        return results
    child_tags = [c for c in root.find_all(recursive=False) if c.name]
    if not child_tags:
        return results
    counts = Counter([c.name for c in child_tags])
    repeated = {name for name, cnt in counts.items() if cnt >= 2}
    if not repeated:
        repeated = set([c.name for c in child_tags]) if len(child_tags) >= 2 else set()
    if not repeated:
        return results
    for idx, child in enumerate(child_tags):
        if child.name not in repeated:
            continue
        name = ""
        for candidate in ("name", "id", "title", "testName", "testname"):
            tag = child.find(candidate)
            if tag and (tag.text or "").strip():
                name = tag.text.strip()
                break
            if child.has_attr(candidate):
                name = child.get(candidate).strip()
                break
        if not name:
            name = child.get("name") or child.get("id") or f"{child.name}-{idx+1}"
        combined_text = " ".join([ (c.text or "").strip() for c in child.find_all(recursive=False) if (c.text or "").strip() ])
        if not combined_text:
            combined_text = (child.text or "").strip()
        lower = (combined_text or "").lower()
        status = "PASS"
        for attr in ("result", "outcome", "status"):
            if child.has_attr(attr) and str(child.get(attr)).strip().lower() in ("fail", "failed", "error"):
                status = "FAIL"
                break
        if any(k in lower for k in ("error", "failed", "exception", "traceback", "assertion")):
            status = "FAIL"
        results.append({
            "testcase": str(name),
            "classname": child.name,
            "time": "",
            "status": status,
            "message": (combined_text[:300] if combined_text else ""),
            "details": (combined_text if combined_text else "")
        })
    return results

def infer_tests_more_aggressive(soup) -> List[Dict]:
    results = []
    root = None
    for tag in soup.find_all():
        root = tag
        break
    if root is None:
        return results

    def node_to_test(node, idx):
        name = ""
        for candidate in ("name", "id", "title", "testName", "testname"):
            if node.has_attr(candidate):
                name = node.get(candidate).strip()
                if name:
                    break
            child = node.find(candidate)
            if child and (child.text or "").strip():
                name = child.text.strip()
                break
        if not name:
            name = node.get("name") or node.get("id") or f"{node.name}-{idx+1}"
        direct_texts = [ (c.text or "").strip() for c in node.find_all(recursive=False) if (c.text or "").strip() ]
        combined_text = " ".join(direct_texts).strip()
        if not combined_text:
            combined_text = (node.text or "").strip()
        lower = (combined_text or "").lower()
        status = "PASS"
        for attr in ("result", "outcome", "status"):
            if node.has_attr(attr) and str(node.get(attr)).strip().lower() in ("fail", "failed", "error"):
                status = "FAIL"
                break
        if any(k in lower for k in ("error", "failed", "exception", "traceback", "assertion", "fault")):
            status = "FAIL"
        return {
            "testcase": str(name),
            "classname": node.name,
            "time": node.get("time") or node.get("duration") or "",
            "status": status,
            "message": (combined_text[:300] if combined_text else ""),
            "details": (combined_text if combined_text else "")
        }

    child_tags = [c for c in root.find_all(recursive=False) if c.name]
    counts = Counter([c.name for c in child_tags])
    repeated = {name for name, cnt in counts.items() if cnt >= 2}
    if repeated:
        idx = 0
        for i, child in enumerate(child_tags):
            if child.name in repeated:
                idx += 1
                results.append(node_to_test(child, idx))
        if results:
            return results

    if len(child_tags) >= 2:
        for i, child in enumerate(child_tags):
            results.append(node_to_test(child, i))
        if results:
            return results

    grandchildren = []
    for c in child_tags:
        grandchildren.extend([g for g in c.find_all(recursive=False) if g.name])
    if grandchildren:
        for i, g in enumerate(grandchildren):
            results.append(node_to_test(g, i))
        if results:
            return results

    all_tags = [t for t in soup.find_all() if t.name]
    if all_tags:
        for i, t in enumerate(all_tags[:100]):
            results.append(node_to_test(t, i))
    return results

# ---------------------------
# Main parsing function
# ---------------------------
def parse_xml_report(path: str) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    content = p.read_text(encoding="utf-8", errors="ignore")
    soup = make_soup(content)

    results = []
    # 1) smart heuristic detection
    nodes = find_test_nodes(soup)
    if nodes:
        for node in nodes:
            results.append(get_test_info(node))
        return results

    # 2) testsuite children
    testsuite = soup.find("testsuite")
    if testsuite:
        for tc in testsuite.find_all(recursive=False):
            if tc.name and is_test_tag(tc.name):
                results.append(get_test_info(tc))
        if results:
            return results

    # 3) repeated sibling inference
    inferred = infer_tests_from_repeated_siblings(soup)
    if inferred:
        return inferred

    # 4) aggressive fallback
    aggressive = infer_tests_more_aggressive(soup)
    if aggressive:
        return aggressive

    return results

# ---------------------------
# Summarize & save
# ---------------------------
def summarize_and_save(results: List[Dict], out_dir: str):
    df = pd.DataFrame(results)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    df.to_csv(Path(out_dir) / "all_tests.csv", index=False)
    fails = df[df["status"].str.upper().isin(["FAIL", "ERROR"])].copy() if not df.empty else df
    if fails.empty:
        print("No failures found.")
        return
    fails["category"] = (fails["message"].fillna("") + " " + fails["details"].fillna("")).apply(categorize_message)
    fails.to_csv(Path(out_dir) / "failure_details.csv", index=False)
    summary = fails.groupby("category").size().reset_index(name="count").sort_values("count", ascending=False)
    summary.to_csv(Path(out_dir) / "failure_summary.csv", index=False)
    print(f"Saved {len(fails)} failures. Summary:\n{summary.to_string(index=False)}")

# ---------------------------
# CLI entrypoint
# ---------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smart Test Report Analyzer")
    parser.add_argument("--input", "-i", required=True, help="Path to XML report file")
    parser.add_argument("--out", "-o", default="output", help="Output folder for CSV files")
    args = parser.parse_args()

    results = parse_xml_report(args.input)
    if not results:
        print("No test cases detected in file.")
        return
    summarize_and_save(results, args.out)

if __name__ == "__main__":
    main()
