 Smart Test Report Analyzer

 Intelligent Regression Failure Insight Tool for QA Engineers

Smart Test Report Analyzer is a Streamlit-powered web app that helps QA engineers and developers analyze automated test result XML files (JUnit, PyTest, TestNG, etc.) with ease.  
It automatically detects pass/fail patterns, extracts insights, and visualizes test outcomes in seconds.

---

 ✨ Features
- 📂 Upload any kind of XML test report (JUnit, PyTest, Selenium, custom)
- 🔍 Automatically detects test cases and parses details
- 📊 Summarizes total, passed, failed, and skipped tests
- 📈 Generates beautiful pie charts and regression analysis
- 🧠 AI-based inference — works even for unstructured XMLs
- 💾 Export results as CSV
- 🎨 Clean and modern Streamlit interface with your logo

---

 🧰 Tech Stack
| Component | Technology |
|------------|-------------|
| Frontend | Streamlit |
| Backend | Python |
| Parsing | BeautifulSoup4 + LXML |
| Visualization | Matplotlib |
| Data Handling | Pandas |

---

 🧪 Example Use Case

| Test Case ID | Description | Expected | Actual | Status |
|---------------|-------------|-----------|---------|--------|
| TC001 | Verify login with valid credentials | Homepage loads | Error page shown | ❌ Fail |
| TC002 | Check forgot password flow | Reset link sent | Reset link sent | ✅ Pass |

➡️ The tool identifies such failures and categorizes causes (assertion, exception, timeout, etc.) automatically.

---

 ⚙️ Local Setup

```bash
git clone https://github.com/<your-username>/smart-test-analyzer.git
cd smart-test-analyzer
pip install -r requirements.txt
streamlit run streamlit_app.py
