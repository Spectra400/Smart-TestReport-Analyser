# analyzer.py
from pathlib import Path
from typing import List, Dict
import re
from collections import Counter
from bs4 import BeautifulSoup
import pandas as pd

# --- parser fallback (XML-aware) ---
def make_soup(content: str):
    preview = content.lstrip()[:400].lower()
    looks_like_xml = preview.startswith("<?xml") or "<testsuite" in preview or "<testcase" in preview or "<testsuites" in preview
    if looks_like_xml:
        # Prefer XML parse; BeautifulSoup(..., "xml") will use lxml if present, else built-in xml parser.
        for parser in ("xml", "lxml", "html.parser"):
            try:
                if parser in ("xml", "lxml"):
                    soup = BeautifulSoup(content, "xml")
                else:
                    soup = BeautifulSoup(content, parser)
                if soup is not None:
                    return soup
            except Exception:
                continue
    # fallback to HTML parsers
    for parser in ("html5lib", "html.parser"):
        try:
            soup = BeautifulSoup(content, parser)
            if soup is not None:
                return soup
        except Exception:
            continue
    return BeautifulSoup(content, "html.parser")

# --- categorization (simple) ---
CATEGORY_PATTERNS = [
    ("Timeout", [r"\btimeout\b", r"timed out"]),
    ("Assertion", [r"assertionerror", r"\bassert\b", r"expected .* but"]),
    ("Element not found", [r"element not found", r"no such element"]),
    ("Auth", [r"unauthorized", r"\b401\b", r"\b403\b"]),
    ("Network", [r"connectionerror", r"connection refused"]),
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

# --- helpers to extract info ---
FAILURE_CHILD_TAGS = {"failure", "error", "failed", "reason", "skipped"}

def extract_text(node):
    if not node:
        return ""
    # attribute messages
    for attr in ("message", "reason", "detail", "details"):
        if node.has_attr(attr):
            return str(node.get(attr)).strip()
    return (node.text or "").strip()

def get_status_and_message(node):
    # check explicit attributes
    for attr in ("status", "result", "outcome"):
        if node.has_attr(attr):
            val = str(node.get(attr)).lower()
            if val in ("fail", "failed", "error"):
                return "FAIL", extract_text(node), node.text or ""
            if val in ("pass", "passed", "ok", "success"):
                return "PASS", "", ""
            if val in ("skipped", "skip", "ignored"):
                return "SKIPPED", "", ""
    # children indicating failure
    for name in FAILURE_CHILD_TAGS:
        found = node.find(name)
        if found:
            msg = extract_text(found) or extract_text(node)
            return ("FAIL", msg, found.text or node.text or "")
    # heuristics in text
    txt = (node.text or "").lower()
    if any(k in txt for k in ("traceback", "assertionerror", "error:", "exception")):
        first = txt.splitlines()[0] if txt.strip() else txt
        return "FAIL", first.strip(), txt.strip()
    return "PASS", "", ""

def get_test_info(node) -> Dict:
    name = node.get("name") or node.get("testName") or node.get("testname") or node.get("id") or ""
    classname = node.get("classname") or node.get("class") or ""
    time = node.get("time") or node.get("duration") or ""
    status, message, details = get_status_and_message(node)
    if not name:
        tag = node.find("name")
        if tag and (tag.text or "").strip():
            name = tag.text.strip()
    return {
        "testcase": str(name).strip(),
        "classname": str(classname).strip(),
        "time": str(time).strip(),
        "status": status,
        "message": (message or "").strip(),
        "details": (details or "").strip(),
    }

# find candidate test nodes
def find_test_nodes(soup) -> List:
    nodes = []
    # common junit testcase
    nodes.extend(soup.find_all("testcase"))
    # any tag with name/testname attribute or test-like tag
    for tag in soup.find_all():
        if tag.get("name") or tag.get("testname") or tag.get("method"):
            nodes.append(tag)
            continue
        if re.search(r"(test|case|testcase|result)", (tag.name or "").lower()):
            nodes.append(tag)
    # dedupe preserving order
    seen = set()
    uniq = []
    for n in nodes:
        key = (n.name, str(n.get("name") or n.get("testname") or ""), id(n))
        if key not in seen:
            uniq.append(n)
            seen.add(key)
    return uniq

# fallback heuristics - repeated siblings
def infer_tests_from_repeated_siblings(soup) -> List[Dict]:
    results = []
    root = soup.find()
    if not root:
        return results
    childs = [c for c in root.find_all(recursive=False) if c.name]
    names = Counter([c.name for c in childs])
    repeated = {n for n, cnt in names.items() if cnt >= 2}
    if not repeated and len(childs) >= 2:
        repeated = set([c.name for c in childs])
    for idx, c in enumerate(childs):
        if c.name not in repeated:
            continue
        info = get_test_info(c)
        if not info["testcase"]:
            info["testcase"] = f"{c.name}-{idx+1}"
        results.append(info)
    return results

def infer_tests_more_aggressive(soup) -> List[Dict]:
    # flatten first 200 tags
    results = []
    all_tags = [t for t in soup.find_all() if t.name][:200]
    for i, t in enumerate(all_tags):
        info = get_test_info(t)
        if info:
            results.append(info)
    return results

# main parse function
def parse_xml_report(path: str) -> List[Dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    content = p.read_text(encoding="utf-8", errors="ignore")
    soup = make_soup(content)
    # 1) direct detection
    nodes = find_test_nodes(soup)
    results = []
    if nodes:
        for n in nodes:
            results.append(get_test_info(n))
        return results
    # 2) testsuite children
    ts = soup.find("testsuite")
    if ts:
        for tc in ts.find_all(recursive=False):
            if tc.name:
                results.append(get_test_info(tc))
        if results:
            return results
    # 3) repeated siblings
    inferred = infer_tests_from_repeated_siblings(soup)
    if inferred:
        return inferred
    # 4) aggressive
    aggressive = infer_tests_more_aggressive(soup)
    if aggressive:
        return aggressive
    return results

# helper to convert to dataframe
def results_to_df(results: List[Dict]):
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    return df
