# 🤖 AI QA Engineer – Automated Code Reviewer & Tester

An intelligent, multi-agent automated system that analyzes codebase repositories, detects structural/logical bugs, evaluates security risks, generates complete test suites, and crafts detailed quality reports. Powered by FastAPI and Google Gemini Pro.

---

## 🚀 Key Features

*   **Multi-Agent Workflow**: Utilizes a coordinated pipeline of dedicated specialized AI agents (Code Loader, Code Analyzer, Test Generator, Bug Analyzer, and Report Agent)[cite: 1].
*   **Static & Deep Code Analysis**: Audits Python files to check for deep structural patterns, custom complexities, bare excepts, or print tracking leaks[cite: 1, 8, 9].
*   **Comprehensive Test Case Generation**: Automatically generates ready-to-run test cases based on actual project functionalities[cite: 1].
*   **Vulnerability & Bug Spotting**: Catches logic mistakes, todo comments, and exposed raw hardcoded credentials immediately[cite: 1].
*   **Dual-Format Reporting**: Produces both structured `JSON` payloads and beautifully formatted interactive `HTML` files for developers[cite: 1].
*   **Sleek Dashboard UI**: Features a modern single-page frontend to monitor systems, submit localized directories, and parse multi-step metrics in real-time.

---

## 🛠️ Architecture & Workflow

The system triggers an orchestrated sequence whenever a repository path is submitted[cite: 1]:
1. **Code Loader Agent**: Discovers local directories, isolates target code, and reads core configuration structures[cite: 1].
2. **Code Analyzer Agent**: Parses raw scripts, tracking system modules, dependencies, and complex functional properties[cite: 1].
3. **Test Generator Agent**: Builds specialized assertions and code validation mocks mapping the evaluated target profiles[cite: 1].
4. **Bug Analyzer Agent**: Runs precise pattern matches targeting potential software runtime exploits and syntactic flaws[cite: 1].
5. **Report Agent**: Merges the aggregate logs to build unified diagnostic dashboards delivered instantly via REST APIs[cite: 1, 3].

---

## 💻 Tech Stack

*   **Backend**: Python, FastAPI, Pydantic, Uvicorn[cite: 3, 7]
*   **AI Engine**: Google GenAI (Gemini Pro Architecture)[cite: 4, 7]
*   **Frontend**: HTML5, Tailwind CSS, Vanilla JavaScript

---

## ⚙️ Installation & Setup

Follow these simple steps to run the complete workspace locally:

### 1. Clone the Repository
```bash
git clone [https://github.com/yourusername/AI_QA_ENGINEER.git](https://github.com/yourusername/AI_QA_ENGINEER.git)
cd AI_QA_ENGINEER
