"""JSON file storage helpers for expenses and monthly budget."""

from datetime import datetime, timedelta
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPENSES_FILE = os.path.join(DATA_DIR, "expenses.json")
BUDGET_FILE = os.path.join(DATA_DIR, "budget.json")

ALLOWED_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Shopping",
    "Entertainment",
    "Other",
]


def backup_corrupted_file(filepath):
    """Rename a corrupted JSON file to <filepath>.bak so fresh data can start."""
    backup_path = filepath + ".bak"
    try:
        if os.path.exists(filepath):
            os.replace(filepath, backup_path)
    except OSError:
        pass


def ensure_data_files():
    """Create the data directory and default JSON files if missing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(EXPENSES_FILE):
        save_expenses([])
    if not os.path.exists(BUDGET_FILE):
        save_budget(0.0)


def load_expenses():
    """Load the list of expenses from JSON, recovering cleanly on corruption."""
    ensure_data_files()
    try:
        with open(EXPENSES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise ValueError("Expenses JSON must be a list")
        return data
    except (json.JSONDecodeError, ValueError, OSError):
        backup_corrupted_file(EXPENSES_FILE)
        save_expenses([])
        return []


def save_expenses(expenses):
    """Write the full expenses list to the JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EXPENSES_FILE, "w", encoding="utf-8") as file:
        json.dump(expenses, file, indent=2)


def load_budget():
    """Load the monthly budget float from JSON, recovering cleanly on corruption."""
    ensure_data_files()
    try:
        with open(BUDGET_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or "monthly_budget" not in data:
            raise ValueError("Budget JSON must be an object with monthly_budget")
        return float(data["monthly_budget"])
    except (json.JSONDecodeError, ValueError, TypeError, OSError):
        backup_corrupted_file(BUDGET_FILE)
        save_budget(0.0)
        return 0.0


def save_budget(monthly_budget):
    """Save the monthly budget value to JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"monthly_budget": round(float(monthly_budget), 2)}
    with open(BUDGET_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def get_next_id(expenses):
    """Return the next integer ID using a simple max + 1 counter."""
    if not expenses:
        return 1
    max_id = 0
    for item in expenses:
        if item.get("id", 0) > max_id:
            max_id = item["id"]
    return max_id + 1


def add_expense(title, amount, category, date_str):
    """Append a new expense dictionary to storage and return it."""
    expenses = load_expenses()
    new_expense = {
        "id": get_next_id(expenses),
        "title": title,
        "amount": round(float(amount), 2),
        "category": category,
        "date": date_str,
    }
    expenses.append(new_expense)
    save_expenses(expenses)
    return new_expense


def update_expense(expense_id, title, amount, category, date_str):
    """Update an existing expense by ID and return it, or None if missing."""
    expenses = load_expenses()
    for item in expenses:
        if item["id"] == expense_id:
            item["title"] = title
            item["amount"] = round(float(amount), 2)
            item["category"] = category
            item["date"] = date_str
            save_expenses(expenses)
            return item
    return None


def delete_expense(expense_id):
    """Delete an expense by ID; return True if removed, False if not found."""
    expenses = load_expenses()
    updated = [item for item in expenses if item["id"] != expense_id]
    if len(updated) == len(expenses):
        return False
    save_expenses(updated)
    return True


def seed_sample_expenses():
    """Seed 20 realistic expenses across the current and previous month."""
    today = datetime.today()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)

    sample_templates = [
        ("Morning Filter Coffee", 120.0, "Food", 0),
        ("Metro Smart Card Recharge", 600.0, "Transport", 1),
        ("Weekly Groceries", 1850.0, "Food", 2),
        ("Broadband Wi-Fi Bill", 999.0, "Bills", 3),
        ("Lunch with Classmates", 480.0, "Food", 4),
        ("Movie Tickets", 640.0, "Entertainment", 5),
        ("Auto Rickshaw Commute", 150.0, "Transport", 6),
        ("Electricity Bill", 2150.0, "Bills", 8),
        ("Python Reference Book", 549.0, "Shopping", 10),
        ("Mobile Postpaid Plan", 599.0, "Bills", 12),
        ("Evening Snacks & Chai", 180.0, "Food", 14),
        ("Campus Printouts & Stationery", 240.0, "Other", 16),
        ("Streaming Subscription", 499.0, "Entertainment", 18),
        ("Running Shoes", 2499.0, "Shopping", 20),
        ("Cab to Railway Station", 380.0, "Transport", 22),
        ("Dinner Delivery", 430.0, "Food", 24),
        ("Previous Month Rent Share", 6500.0, "Bills", None),
        ("Supermarket Monthly Stock", 2300.0, "Food", None),
        ("Bus Pass Renewal", 750.0, "Transport", None),
        ("Headphones Replacement", 1299.0, "Shopping", None),
    ]

    expenses = load_expenses()
    next_id = get_next_id(expenses)
    created = []
    prev_days = [5, 11, 18, 25]
    prev_index = 0

    for title, amount, category, day_offset in sample_templates:
        if day_offset is not None:
            target_date = today - timedelta(days=min(day_offset, today.day - 1))
        else:
            day_num = min(prev_days[prev_index], last_month_end.day)
            target_date = last_month_end.replace(day=day_num)
            prev_index += 1

        entry = {
            "id": next_id,
            "title": title,
            "amount": amount,
            "category": category,
            "date": target_date.strftime("%Y-%m-%d"),
        }
        expenses.append(entry)
        created.append(entry)
        next_id += 1

    save_expenses(expenses)
    if load_budget() <= 0:
        save_budget(18000.0)
    return created
