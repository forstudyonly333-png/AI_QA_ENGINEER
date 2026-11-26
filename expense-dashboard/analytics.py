"""Pure analytics and validation functions for the expense dashboard."""

from datetime import datetime, timedelta


def parse_date(date_str):
    """Parse a YYYY-MM-DD date string and return a datetime object."""
    if not isinstance(date_str, str) or not date_str.strip():
        raise ValueError("Date must be in YYYY-MM-DD format")
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid date. Expected YYYY-MM-DD format")


def validate_expense_data(data, allowed_categories):
    """Validate and normalize an expense payload dictionary."""
    if not isinstance(data, dict):
        raise ValueError("Invalid request payload")
    title = str(data.get("title", "")).strip()
    if not title:
        raise ValueError("Title must not be empty")
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        raise ValueError("Amount must be a number greater than 0")
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    category = str(data.get("category", "")).strip()
    if category not in allowed_categories:
        raise ValueError("Invalid category selected")
    parsed_date = parse_date(data.get("date", ""))
    return {
        "title": title,
        "amount": round(amount, 2),
        "category": category,
        "date": parsed_date.strftime("%Y-%m-%d"),
    }


def filter_expenses(expenses, start_date=None, end_date=None, category=None):
    """Filter expenses by optional date range and category, sorted newest first."""
    start_dt = parse_date(start_date) if start_date else None
    end_dt = parse_date(end_date) if end_date else None
    if start_dt and end_dt and start_dt > end_dt:
        raise ValueError("Start date must not be after end date")

    result = []
    for item in expenses:
        item_dt = parse_date(item["date"])
        if start_dt and item_dt < start_dt:
            continue
        if end_dt and item_dt > end_dt:
            continue
        if category and category != "All" and item["category"] != category:
            continue
        result.append(item)

    result.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    return result


def category_totals(expenses):
    """Calculate total spending for each category present in expenses."""
    totals = {}
    for item in expenses:
        cat = item["category"]
        totals[cat] = round(totals.get(cat, 0.0) + float(item["amount"]), 2)
    return totals


def category_percentages(totals):
    """Calculate percentage share of spending for each category."""
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return {cat: 0.0 for cat in totals}
    percentages = {}
    for cat, amount in totals.items():
        percentages[cat] = round((amount / grand_total) * 100, 1)
    return percentages


def days_in_month(year, month):
    """Return the number of days in the given year and month."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day


def daily_totals(expenses, year, month):
    """Return a dict mapping each day (1..days) of a month to total spending."""
    total_days = days_in_month(year, month)
    totals = {day: 0.0 for day in range(1, total_days + 1)}
    prefix = f"{year:04d}-{month:02d}-"
    for item in expenses:
        if item["date"].startswith(prefix):
            day = int(item["date"].split("-")[2])
            totals[day] = round(totals[day] + float(item["amount"]), 2)
    return totals


def month_total(expenses, year, month):
    """Calculate total spending for the specified year and month."""
    prefix = f"{year:04d}-{month:02d}-"
    total = 0.0
    for item in expenses:
        if item["date"].startswith(prefix):
            total += float(item["amount"])
    return round(total, 2)


def budget_status(spent, budget):
    """Compute percent used, remaining amount, and alert level for a budget."""
    if budget is None or budget <= 0:
        return {"percent_used": 0.0, "remaining": 0.0, "level": "ok"}
    raw_percent = (spent / budget) * 100
    percent_used = round(raw_percent, 1)
    remaining = round(budget - spent, 2)
    if raw_percent >= 100:
        level = "exceeded"
    elif raw_percent >= 80:
        level = "warning"
    else:
        level = "ok"
    return {
        "percent_used": percent_used,
        "remaining": remaining,
        "level": level,
    }
