# Viva Study Notes — Personal Expense & Budget Analytics Dashboard

## 1. Program Flow

1. **Startup (`app.py` -> `storage.py`)**:
   - When `python app.py` runs, `app.py` calls `storage.ensure_data_files()`.
   - If `data/expenses.json` or `data/budget.json` does not exist, `storage.py` creates them with default values (`[]` and `{"monthly_budget": 0.0}`).
2. **Page Load (`GET /` -> `static/app.js`)**:
   - Browser requests `/`, and Flask renders `templates/index.html`.
   - `app.js` runs `initDashboard()`, sets default dates (today and current month), and calls `/api/expenses` and `/api/summary` using `fetch()`.
3. **Adding / Editing / Deleting an Expense**:
   - User submits a form in the browser -> `app.js` sends JSON via `fetch()` (`POST`, `PUT`, or `DELETE`).
   - `app.py` validates input using `analytics.validate_expense_data()` inside a `try-except` block.
   - `storage.py` loads `expenses.json`, updates the list in memory, writes it back with `json.dump()`, and returns the result.
   - `app.js` immediately re-fetches data to refresh the summary cards, alert banner, charts, and table without reloading the page.
4. **Budget & Alerts**:
   - `analytics.month_total()` sums expenses for the selected month.
   - `analytics.budget_status()` calculates `percent_used`, `remaining`, and `level` (`"ok"`, `"warning"` at >=80%, `"exceeded"` at >=100%).
5. **CSV Export (`GET /api/export`)**:
   - `app.py` filters expenses using `analytics.filter_expenses()`, writes rows into an in-memory `io.StringIO` buffer using `csv.writer()`, and sends it as `expenses.csv`.

---

## 2. Python Concepts Mapped to Code

| Python Concept | File | Function(s) | How It Is Used |
| :--- | :--- | :--- | :--- |
| **Lists** | `storage.py`, `analytics.py` | `load_expenses`, `filter_expenses`, `delete_expense` | Stores all expense records as a list of dictionaries; builds filtered lists and removes matching IDs with list comprehensions. |
| **Dictionaries** | `storage.py`, `analytics.py` | `add_expense`, `category_totals`, `daily_totals`, `budget_status` | Each expense (`{"id", "title", "amount", "category", "date"}`), category totals, daily totals, and API JSON responses use dictionaries. |
| **Functions** | `analytics.py`, `storage.py`, `app.py` | All functions (e.g., `month_total`, `save_expenses`, `create_expense`) | Separates routing (`app.py`), file I/O (`storage.py`), and pure calculations (`analytics.py`) into small reusable functions. |
| **Loops (`for`)** | `analytics.py`, `storage.py`, `app.py` | `filter_expenses`, `category_totals`, `get_next_id`, `export_csv` | Iterates over expenses to filter, sum category amounts, find the max ID, and write CSV rows. |
| **Conditionals (`if/elif/else`)** | `analytics.py`, `storage.py` | `budget_status`, `validate_expense_data`, `days_in_month` | Checks validation rules, handles 0 budget safely, and assigns `"ok"`, `"warning"`, or `"exceeded"` alert levels. |
| **`try-except`** | `analytics.py`, `storage.py`, `app.py` | `parse_date`, `load_expenses`, `load_budget`, `create_expense` | Catches invalid dates (`ValueError`), corrupted JSON (`json.JSONDecodeError`), and missing/bad user input without crashing the server. |
| **`datetime`** | `analytics.py`, `storage.py`, `app.py` | `parse_date`, `days_in_month`, `seed_sample_expenses` | Parses `"YYYY-MM-DD"` strings via `datetime.strptime()`, calculates days in a month with `timedelta`, and picks current/past month dates. |
| **`json`** | `storage.py` | `load_expenses`, `save_expenses`, `load_budget`, `save_budget` | Reads and writes Python lists/dicts to `.json` files using `json.load()` and `json.dump()`. |
| **`csv` & `io`** | `app.py` | `export_csv` | Uses `io.StringIO()` as an in-memory text buffer and `csv.writer()` to generate downloadable CSV output. |
| **File Handling (`os` & `open`)** | `storage.py` | `ensure_data_files`, `backup_corrupted_file`, `save_expenses` | Uses `os.makedirs`, `os.path.exists`, `os.replace`, and `with open(..., encoding="utf-8")` to safely read, write, and back up files. |

---

## 3. Likely Viva Questions & Short Answers

1. **Why did you split the backend into `app.py`, `storage.py`, and `analytics.py`?**  
   For separation of concerns: `app.py` handles HTTP routes, `storage.py` handles JSON file persistence, and `analytics.py` contains pure calculation functions that are easy to test with `unittest`.

2. **Why is `analytics.py` made of pure functions?**  
   Pure functions take inputs and return outputs without modifying files or global state, which makes them predictable and easy to unit test without setting up Flask or disk files.

3. **How do you ensure each expense gets a unique ID?**  
   `get_next_id()` loops through the existing expenses list, finds the maximum `id`, and returns `max_id + 1` (or `1` if the list is empty).

4. **What happens if `data/expenses.json` is deleted or corrupted?**  
   If missing, `ensure_data_files()` creates an empty `[]`. If corrupted, `load_expenses()` catches `json.JSONDecodeError`, renames the broken file to `expenses.json.bak` using `os.replace()`, and creates a fresh empty list.

5. **How do you validate dates in Python?**  
   `parse_date()` calls `datetime.strptime(date_str, "%Y-%m-%d")`, which rejects both wrong formats (like `27-11-2026`) and impossible calendar dates (like `2026-02-30`) by raising `ValueError`.

6. **How do you prevent division by zero in `budget_status()` and `category_percentages()`?**  
   In `budget_status()`, if `budget <= 0`, it returns `0.0%` immediately before dividing. In `category_percentages()`, if `grand_total <= 0`, it returns `0.0` for all categories.

7. **How does the budget alert threshold logic work?**  
   `budget_status()` calculates `(spent / budget) * 100`. Below `80%` returns `"ok"`, `80%` up to `100%` returns `"warning"` (yellow banner), and `100%` or more returns `"exceeded"` (red banner).

8. **How are expenses sorted in `GET /api/expenses`?**  
   `filter_expenses()` uses `result.sort(key=lambda x: (x["date"], x["id"]), reverse=True)`, sorting by date newest first and breaking same-day ties by newest ID.

9. **Why do you use `io.StringIO()` when exporting CSV?**  
   `csv.writer()` expects a file-like text stream. `io.StringIO()` lets us build the CSV string in memory without creating temporary files on disk, then send it directly in the Flask `Response`.

10. **What HTTP status codes does your API return and why?**  
    `200` for successful reads/updates/deletes/exports, `201` for creating a new resource (`POST /api/expenses` and `/api/sample`), `400` for validation errors, and `404` when an expense ID does not exist.

11. **How does the frontend update without reloading the whole page?**  
    `static/app.js` uses the browser's `fetch()` API to send asynchronous JSON requests to Flask, then updates the DOM table, cards, alert banner, and Chart.js instances in place.

12. **How do you calculate the number of days in a month without hardcoding 30 or 31?**  
    `days_in_month(year, month)` finds the 1st day of the next month and subtracts `timedelta(days=1)`, which automatically handles 28, 29 (leap years), 30, and 31-day months.

---

## 4. Three Possible Improvements

1. **SQLite Database Migration**: Replace JSON files with SQLite (`sqlite3` in Python's standard library) to handle thousands of transactions with faster queries and safe concurrent writes.
2. **Recurring Expenses & Category Budgets**: Allow setting per-category monthly limits (e.g., Food ₹5,000) and automatically repeating monthly bills like rent or Wi-Fi.
3. **User Authentication**: Add login/registration with `werkzeug.security` password hashing so multiple users can maintain separate expense dashboards.
