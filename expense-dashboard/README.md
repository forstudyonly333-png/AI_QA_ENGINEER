# Personal Expense & Budget Analytics Dashboard

A lightweight, beginner-friendly full-stack web application built with **Python 3.10+**, **Flask**, JSON file storage, and a responsive HTML/CSS/JavaScript frontend using **Chart.js**.

Designed for **Programming Fundamentals using Python - Part 1**, the backend uses plain functions, lists, dictionaries, loops, conditionals, and standard-library modules (`json`, `csv`, `datetime`, `os`, `io`) without any database or heavy frameworks.

---

## Features

- **Add, Edit & Delete Expenses**: Full CRUD support with server-side and client-side validation (`₹` INR formatting).
- **Monthly Budget Tracking & Alerts**:
  - Summary cards for Total Spent, Monthly Budget, Remaining Balance, and `% Used`.
  - Yellow warning banner at **80%–99.9%** budget usage and red alert banner at **100%+**.
- **Interactive Analytics Charts (Chart.js)**:
  - **Category Breakdown Doughnut Chart** with percentage tooltips.
  - **Daily Spending Bar Chart** for the selected month with a dashed **Daily Budget Reference Line** (`monthly_budget / days_in_month`).
- **Filtering & CSV Export**: Filter transactions by start date, end date, and category; export the active filtered view to `expenses.csv`.
- **Resilient JSON Storage**: Auto-creates `data/expenses.json` and `data/budget.json` on first run and backs up corrupted files to `.bak` automatically.
- **One-Click Sample Data**: Seed 20 realistic expenses across the last two months via `/api/sample`.

---

## Folder Structure

```text
expense-dashboard/
  app.py                  # Flask routes only (no business logic)
  storage.py              # JSON load/save, CRUD helpers, corrupted-file backup
  analytics.py            # Pure functions for filtering, totals, percentages, budget status
  data/
    expenses.json         # Auto-created on first run
    budget.json           # Auto-created on first run
  static/
    styles.css            # Responsive dashboard styling
    app.js                # fetch() API calls, DOM updates, Chart.js rendering
  templates/
    index.html            # Dashboard UI template
  tests/
    test_analytics.py     # unittest suite for analytics and validation
  requirements.txt        # Flask dependency
  README.md
  VIVA_NOTES.md
```

---

## Setup & Installation

1. Open a terminal inside the `expense-dashboard` folder:
   ```bash
   cd expense-dashboard
   ```

2. Create and activate a virtual environment:
   - **Windows (PowerShell / CMD):**
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## How to Run

Start the Flask development server:

```bash
python app.py
```

Then open your browser and visit:

```text
http://127.0.0.1:5000
```

---

## How to Run Tests

Run the `unittest` suite from inside `expense-dashboard/`:

```bash
python -m unittest discover tests
```

---

## API Reference

| Method | Endpoint | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Render the dashboard HTML page | `200` |
| `GET` | `/api/expenses` | List expenses (optional `start_date`, `end_date`, `category`), sorted newest first | `200`, `400` |
| `POST` | `/api/expenses` | Validate and add a new expense | `201`, `400` |
| `PUT` | `/api/expenses/<id>` | Validate and update an existing expense | `200`, `400`, `404` |
| `DELETE` | `/api/expenses/<id>` | Delete an expense by ID | `200`, `404` |
| `GET` | `/api/budget` | Return monthly budget, current month spent, remaining, `% used`, and alert level | `200`, `400` |
| `POST` | `/api/budget` | Set a positive monthly budget (`{"monthly_budget": number}`) | `200`, `400` |
| `GET` | `/api/summary` | Return category totals, percentages, daily totals for selected month, and total spent | `200`, `400` |
| `GET` | `/api/export` | Download filtered expenses as `expenses.csv` | `200`, `400` |
| `POST` | `/api/sample` | Seed 20 realistic expenses across the last two months | `201` |
