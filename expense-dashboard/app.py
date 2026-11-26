"""Flask routes for the Personal Expense & Budget Analytics Dashboard."""

import csv
from datetime import datetime
import io
import os
from flask import Flask, Response, jsonify, render_template, request

import analytics
import storage

app = Flask(__name__)
storage.ensure_data_files()


def get_selected_year_month():
    """Read optional year and month query parameters, defaulting to today."""
    today = datetime.today()
    year_raw = request.args.get("year")
    month_raw = request.args.get("month")
    try:
        year = int(year_raw) if year_raw else today.year
        month = int(month_raw) if month_raw else today.month
    except ValueError:
        raise ValueError("Year and month must be valid integers")
    if month < 1 or month > 12 or year < 1900 or year > 2100:
        raise ValueError("Month must be 1-12 and year must be valid")
    return year, month


@app.route("/")
def index():
    """Render the main dashboard page."""
    return render_template("index.html", categories=storage.ALLOWED_CATEGORIES)


@app.route("/api/expenses", methods=["GET"])
def list_expenses():
    """Return filtered expenses sorted by date, newest first."""
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None
    category = request.args.get("category") or None
    try:
        expenses = storage.load_expenses()
        filtered = analytics.filter_expenses(expenses, start_date, end_date, category)
        return jsonify(filtered), 200
    except ValueError as err:
        return jsonify({"error": str(err)}), 400


@app.route("/api/expenses", methods=["POST"])
def create_expense():
    """Validate input and add a new expense."""
    payload = request.get_json(silent=True)
    try:
        cleaned = analytics.validate_expense_data(payload, storage.ALLOWED_CATEGORIES)
        created = storage.add_expense(
            cleaned["title"],
            cleaned["amount"],
            cleaned["category"],
            cleaned["date"],
        )
        return jsonify(created), 201
    except ValueError as err:
        return jsonify({"error": str(err)}), 400


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def edit_expense(expense_id):
    """Validate input and update an existing expense by ID."""
    payload = request.get_json(silent=True)
    try:
        cleaned = analytics.validate_expense_data(payload, storage.ALLOWED_CATEGORIES)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    updated = storage.update_expense(
        expense_id,
        cleaned["title"],
        cleaned["amount"],
        cleaned["category"],
        cleaned["date"],
    )
    if updated is None:
        return jsonify({"error": "Expense not found"}), 404
    return jsonify(updated), 200


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def remove_expense(expense_id):
    """Delete an expense by ID, returning 404 if it does not exist."""
    deleted = storage.delete_expense(expense_id)
    if not deleted:
        return jsonify({"error": "Expense not found"}), 404
    return jsonify({"message": "Expense deleted"}), 200


@app.route("/api/budget", methods=["GET"])
def get_budget():
    """Return the monthly budget and current month usage metrics."""
    try:
        year, month = get_selected_year_month()
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    expenses = storage.load_expenses()
    monthly_budget = storage.load_budget()
    spent = analytics.month_total(expenses, year, month)
    status = analytics.budget_status(spent, monthly_budget)
    return jsonify(
        {
            "monthly_budget": monthly_budget,
            "spent": spent,
            "year": year,
            "month": month,
            **status,
        }
    ), 200


@app.route("/api/budget", methods=["POST"])
def set_budget():
    """Set a new positive monthly budget."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid request payload"}), 400
    try:
        amount = float(payload.get("monthly_budget", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Monthly budget must be a positive number"}), 400

    if amount <= 0:
        return jsonify({"error": "Monthly budget must be greater than 0"}), 400

    storage.save_budget(amount)
    today = datetime.today()
    expenses = storage.load_expenses()
    spent = analytics.month_total(expenses, today.year, today.month)
    status = analytics.budget_status(spent, amount)
    return jsonify(
        {
            "monthly_budget": round(amount, 2),
            "spent": spent,
            **status,
        }
    ), 200


@app.route("/api/summary", methods=["GET"])
def get_summary():
    """Return category totals, percentages, daily totals, and total spent."""
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None
    category = request.args.get("category") or None
    try:
        year, month = get_selected_year_month()
        expenses = storage.load_expenses()
        filtered = analytics.filter_expenses(expenses, start_date, end_date, category)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    totals = analytics.category_totals(filtered)
    percentages = analytics.category_percentages(totals)
    daily = analytics.daily_totals(expenses, year, month)
    total_spent = round(sum(float(item["amount"]) for item in filtered), 2)
    month_spent = analytics.month_total(expenses, year, month)
    monthly_budget = storage.load_budget()
    status = analytics.budget_status(month_spent, monthly_budget)

    return jsonify(
        {
            "year": year,
            "month": month,
            "total_spent": total_spent,
            "month_spent": month_spent,
            "category_totals": totals,
            "category_percentages": percentages,
            "daily_totals": daily,
            "days_in_month": len(daily),
            "monthly_budget": monthly_budget,
            "budget_status": status,
        }
    ), 200


@app.route("/api/export", methods=["GET"])
def export_csv():
    """Download filtered expenses as a CSV file."""
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None
    category = request.args.get("category") or None
    try:
        expenses = storage.load_expenses()
        filtered = analytics.filter_expenses(expenses, start_date, end_date, category)
    except ValueError as err:
        return jsonify({"error": str(err)}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Amount (INR)", "Category", "Date"])
    for item in filtered:
        writer.writerow(
            [item["id"], item["title"], item["amount"], item["category"], item["date"]]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )


@app.route("/api/sample", methods=["POST"])
def load_sample_data():
    """Seed 20 realistic expenses across the last two months."""
    created = storage.seed_sample_expenses()
    return jsonify(
        {
            "message": f"Added {len(created)} sample expenses",
            "count": len(created),
        }
    ), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("PORT") is None)
