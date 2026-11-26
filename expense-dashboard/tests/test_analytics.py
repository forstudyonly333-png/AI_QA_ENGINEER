"""Unit tests for pure analytics and validation functions."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics


class TestAnalytics(unittest.TestCase):
    """Test cases for analytics.py functions."""

    def setUp(self):
        self.sample_expenses = [
            {"id": 1, "title": "Lunch", "amount": 250.0, "category": "Food", "date": "2026-11-05"},
            {"id": 2, "title": "Metro", "amount": 150.0, "category": "Transport", "date": "2026-11-05"},
            {"id": 3, "title": "Groceries", "amount": 600.0, "category": "Food", "date": "2026-11-12"},
            {"id": 4, "title": "Electricity", "amount": 1000.0, "category": "Bills", "date": "2026-10-20"},
        ]

    def test_filter_by_date_range(self):
        result = analytics.filter_expenses(
            self.sample_expenses, start_date="2026-11-01", end_date="2026-11-10"
        )
        self.assertEqual(len(result), 2)
        self.assertEqual([item["id"] for item in result], [2, 1])

    def test_filter_by_category(self):
        result = analytics.filter_expenses(self.sample_expenses, category="Food")
        self.assertEqual(len(result), 2)
        self.assertTrue(all(item["category"] == "Food" for item in result))

    def test_filter_sorted_newest_first(self):
        result = analytics.filter_expenses(self.sample_expenses)
        dates = [item["date"] for item in result]
        self.assertEqual(dates, ["2026-11-12", "2026-11-05", "2026-11-05", "2026-10-20"])

    def test_category_totals(self):
        totals = analytics.category_totals(self.sample_expenses)
        self.assertEqual(totals["Food"], 850.0)
        self.assertEqual(totals["Transport"], 150.0)
        self.assertEqual(totals["Bills"], 1000.0)

    def test_category_percentages(self):
        totals = analytics.category_totals(self.sample_expenses)
        percentages = analytics.category_percentages(totals)
        self.assertEqual(percentages["Food"], 42.5)
        self.assertEqual(percentages["Transport"], 7.5)
        self.assertEqual(percentages["Bills"], 50.0)

    def test_category_percentages_empty(self):
        self.assertEqual(analytics.category_percentages({}), {})
        self.assertEqual(analytics.category_percentages({"Food": 0.0}), {"Food": 0.0})

    def test_budget_status_below_80_percent(self):
        status = analytics.budget_status(7900.0, 10000.0)
        self.assertEqual(status["percent_used"], 79.0)
        self.assertEqual(status["remaining"], 2100.0)
        self.assertEqual(status["level"], "ok")

    def test_budget_status_at_80_percent(self):
        status = analytics.budget_status(8000.0, 10000.0)
        self.assertEqual(status["percent_used"], 80.0)
        self.assertEqual(status["remaining"], 2000.0)
        self.assertEqual(status["level"], "warning")

    def test_budget_status_at_100_percent(self):
        status = analytics.budget_status(10000.0, 10000.0)
        self.assertEqual(status["percent_used"], 100.0)
        self.assertEqual(status["remaining"], 0.0)
        self.assertEqual(status["level"], "exceeded")

    def test_budget_status_zero_budget(self):
        status = analytics.budget_status(500.0, 0.0)
        self.assertEqual(status["percent_used"], 0.0)
        self.assertEqual(status["remaining"], 0.0)
        self.assertEqual(status["level"], "ok")

    def test_daily_totals(self):
        daily = analytics.daily_totals(self.sample_expenses, 2026, 11)
        self.assertEqual(len(daily), 30)
        self.assertEqual(daily[5], 400.0)
        self.assertEqual(daily[12], 600.0)
        self.assertEqual(daily[1], 0.0)

    def test_month_total(self):
        nov_total = analytics.month_total(self.sample_expenses, 2026, 11)
        oct_total = analytics.month_total(self.sample_expenses, 2026, 10)
        self.assertEqual(nov_total, 1000.0)
        self.assertEqual(oct_total, 1000.0)

    def test_invalid_date_format_raises(self):
        with self.assertRaises(ValueError):
            analytics.parse_date("27-11-2026")
        with self.assertRaises(ValueError):
            analytics.filter_expenses(self.sample_expenses, start_date="2026-02-30")

    def test_start_date_after_end_date_raises(self):
        with self.assertRaises(ValueError):
            analytics.filter_expenses(
                self.sample_expenses, start_date="2026-11-20", end_date="2026-11-01"
            )


if __name__ == "__main__":
    unittest.main()
