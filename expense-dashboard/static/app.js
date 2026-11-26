const CATEGORY_COLORS = {
  Food: "#2563eb",
  Transport: "#0ea5e9",
  Bills: "#f59e0b",
  Shopping: "#8b5cf6",
  Entertainment: "#ec4899",
  Other: "#64748b",
};

let categoryChart = null;
let dailyChart = null;
let currentExpenses = [];

function formatINR(value) {
  const num = Number(value) || 0;
  return "₹" + num.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function getTodayISO() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getCurrentMonthValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

function getSelectedYearMonth() {
  const monthInput = document.getElementById("month-selector").value || getCurrentMonthValue();
  const [year, month] = monthInput.split("-").map(Number);
  return { year, month };
}

function getActiveFilters() {
  return {
    start_date: document.getElementById("filter-start").value,
    end_date: document.getElementById("filter-end").value,
    category: document.getElementById("filter-category").value,
  };
}

function buildFilterQuery(includeMonth = false) {
  const params = new URLSearchParams();
  const filters = getActiveFilters();
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  if (filters.category && filters.category !== "All") {
    params.set("category", filters.category);
  }
  if (includeMonth) {
    const { year, month } = getSelectedYearMonth();
    params.set("year", String(year));
    params.set("month", String(month));
  }
  return params.toString();
}

function setFormMessage(elementId, text, type = "") {
  const el = document.getElementById(elementId);
  el.textContent = text;
  el.className = "form-message" + (type ? ` ${type}` : "");
}

function validateExpenseInputs(title, amount, category, dateStr) {
  if (!title.trim()) return "Please enter an expense title.";
  const num = Number(amount);
  if (!amount || Number.isNaN(num) || num <= 0) {
    return "Amount must be a number greater than 0.";
  }
  if (!category) return "Please select a category.";
  if (!dateStr) return "Please choose a valid date.";
  return "";
}

async function fetchDashboardData() {
  const filterErrEl = document.getElementById("filter-error-msg");
  filterErrEl.classList.add("hidden");
  filterErrEl.textContent = "";

  const expenseQuery = buildFilterQuery(false);
  const summaryQuery = buildFilterQuery(true);

  try {
    const [expRes, sumRes] = await Promise.all([
      fetch(`/api/expenses${expenseQuery ? "?" + expenseQuery : ""}`),
      fetch(`/api/summary${summaryQuery ? "?" + summaryQuery : ""}`),
    ]);

    const expData = await expRes.json();
    const sumData = await sumRes.json();

    if (!expRes.ok) {
      filterErrEl.textContent = expData.error || "Unable to load expenses.";
      filterErrEl.classList.remove("hidden");
      return;
    }
    if (!sumRes.ok) {
      filterErrEl.textContent = sumData.error || "Unable to load summary.";
      filterErrEl.classList.remove("hidden");
      return;
    }

    currentExpenses = expData;
    renderExpensesTable(expData);
    renderSummaryCards(sumData);
    renderBudgetAlert(sumData);
    renderCategoryChart(sumData);
    renderDailyChart(sumData);
  } catch (err) {
    filterErrEl.textContent = "Network error while loading dashboard data.";
    filterErrEl.classList.remove("hidden");
  }
}

function renderSummaryCards(summary) {
  const status = summary.budget_status;
  const budget = Number(summary.monthly_budget) || 0;
  const days = summary.days_in_month || 30;
  const monthLabel = new Date(summary.year, summary.month - 1, 1).toLocaleString("en-IN", {
    month: "long",
    year: "numeric",
  });

  document.getElementById("card-spent").textContent = formatINR(summary.month_spent);
  document.getElementById("card-month-name").textContent = monthLabel;
  document.getElementById("card-budget").textContent = formatINR(budget);
  document.getElementById("card-daily-limit").textContent =
    budget > 0 ? `Daily target: ${formatINR(budget / days)}` : "No budget set";

  if (budget > 0) {
    document.getElementById("card-remaining").textContent = formatINR(status.remaining);
    document.getElementById("card-remaining-note").textContent =
      status.remaining < 0 ? "Over monthly budget" : "Available for month";
  } else {
    document.getElementById("card-remaining").textContent = "₹0.00";
    document.getElementById("card-remaining-note").textContent = "Set a budget to track";
  }

  document.getElementById("card-percent").textContent = `${status.percent_used.toFixed(1)}%`;
  const bar = document.getElementById("budget-progress-bar");
  bar.style.width = `${Math.min(status.percent_used, 100)}%`;
  bar.className = "progress-fill" + (status.level !== "ok" ? ` ${status.level}` : "");

  if (!document.getElementById("budget-input").value && budget > 0) {
    document.getElementById("budget-input").value = budget;
  }
}

function renderBudgetAlert(summary) {
  const banner = document.getElementById("budget-alert");
  const textEl = document.getElementById("budget-alert-text");
  const status = summary.budget_status;
  const budget = Number(summary.monthly_budget) || 0;

  if (budget <= 0 || status.level === "ok") {
    banner.className = "alert-banner hidden";
    textEl.textContent = "";
    return;
  }

  if (status.level === "exceeded") {
    banner.className = "alert-banner exceeded";
    textEl.textContent = `Budget exceeded! You have used ${status.percent_used.toFixed(1)}% (${formatINR(summary.month_spent)} of ${formatINR(budget)}).`;
  } else {
    banner.className = "alert-banner warning";
    textEl.textContent = `Budget warning: You have used ${status.percent_used.toFixed(1)}% of your ${formatINR(budget)} monthly budget.`;
  }
}

function renderExpensesTable(expenses) {
  const tbody = document.getElementById("expenses-tbody");
  const emptyState = document.getElementById("empty-state");
  tbody.innerHTML = "";

  if (!expenses.length) {
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");

  for (const item of expenses) {
    const tr = document.createElement("tr");

    const dateTd = document.createElement("td");
    dateTd.textContent = item.date;

    const titleTd = document.createElement("td");
    titleTd.textContent = item.title;

    const catTd = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "category-badge";
    badge.textContent = item.category;
    catTd.appendChild(badge);

    const amtTd = document.createElement("td");
    amtTd.className = "text-right";
    amtTd.textContent = formatINR(item.amount);

    const actionsTd = document.createElement("td");
    actionsTd.className = "actions-cell";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-edit-sm";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => openEditModal(item));

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "btn btn-danger-sm";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", () => handleDeleteExpense(item));

    actionsTd.appendChild(editBtn);
    actionsTd.appendChild(delBtn);

    tr.appendChild(dateTd);
    tr.appendChild(titleTd);
    tr.appendChild(catTd);
    tr.appendChild(amtTd);
    tr.appendChild(actionsTd);
    tbody.appendChild(tr);
  }
}

function renderCategoryChart(summary) {
  const totals = summary.category_totals || {};
  const percentages = summary.category_percentages || {};
  const labels = Object.keys(totals);
  const values = Object.values(totals);
  const emptyEl = document.getElementById("category-chart-empty");

  document.getElementById("filtered-total-label").textContent =
    `Filtered: ${formatINR(summary.total_spent)}`;

  if (categoryChart) {
    categoryChart.destroy();
    categoryChart = null;
  }

  if (!labels.length) {
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  const ctx = document.getElementById("category-chart").getContext("2d");
  categoryChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: labels.map((cat) => CATEGORY_COLORS[cat] || "#94a3b8"),
          borderWidth: 2,
          borderColor: "#ffffff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctxItem) => {
              const cat = ctxItem.label;
              const pct = percentages[cat] ?? 0;
              return `${cat}: ${formatINR(ctxItem.raw)} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

function renderDailyChart(summary) {
  const daily = summary.daily_totals || {};
  const days = Object.keys(daily).map(Number).sort((a, b) => a - b);
  const amounts = days.map((day) => daily[String(day)] || 0);
  const budget = Number(summary.monthly_budget) || 0;
  const dailyLimit = budget > 0 && days.length > 0 ? Number((budget / days.length).toFixed(2)) : null;

  document.getElementById("daily-budget-label").textContent =
    dailyLimit !== null
      ? `Daily budget line: ${formatINR(dailyLimit)} / day`
      : "Daily budget line: Not set";

  if (dailyChart) {
    dailyChart.destroy();
    dailyChart = null;
  }

  const datasets = [
    {
      label: "Daily Spend (₹)",
      data: amounts,
      backgroundColor: "#3b82f6",
      borderRadius: 4,
      order: 2,
    },
  ];

  if (dailyLimit !== null) {
    datasets.push({
      type: "line",
      label: `Daily Budget (${formatINR(dailyLimit)})`,
      data: days.map(() => dailyLimit),
      borderColor: "#ef4444",
      borderWidth: 2,
      borderDash: [6, 5],
      pointRadius: 0,
      fill: false,
      order: 1,
    });
  }

  const ctx = document.getElementById("daily-chart").getContext("2d");
  dailyChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: days.map((d) => String(d)),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: { display: true, text: "Day of Month" },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: {
            callback: (val) => "₹" + Number(val).toLocaleString("en-IN"),
          },
        },
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctxItem) => `${ctxItem.dataset.label}: ${formatINR(ctxItem.raw)}`,
          },
        },
      },
    },
  });
}

async function handleAddExpense(event) {
  event.preventDefault();
  const title = document.getElementById("expense-title").value;
  const amount = document.getElementById("expense-amount").value;
  const category = document.getElementById("expense-category").value;
  const dateStr = document.getElementById("expense-date").value;

  const clientError = validateExpenseInputs(title, amount, category, dateStr);
  if (clientError) {
    setFormMessage("expense-form-msg", clientError, "error");
    return;
  }

  try {
    const res = await fetch("/api/expenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        amount: Number(amount),
        category,
        date: dateStr,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setFormMessage("expense-form-msg", data.error || "Could not add expense.", "error");
      return;
    }

    document.getElementById("expense-title").value = "";
    document.getElementById("expense-amount").value = "";
    document.getElementById("expense-date").value = getTodayISO();
    setFormMessage("expense-form-msg", "Expense added!", "success");
    await fetchDashboardData();
  } catch (err) {
    setFormMessage("expense-form-msg", "Network error while saving expense.", "error");
  }
}

async function handleSaveBudget(event) {
  event.preventDefault();
  const rawVal = document.getElementById("budget-input").value;
  const amount = Number(rawVal);

  if (!rawVal || Number.isNaN(amount) || amount <= 0) {
    setFormMessage("budget-form-msg", "Monthly budget must be greater than 0.", "error");
    return;
  }

  try {
    const res = await fetch("/api/budget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthly_budget: amount }),
    });
    const data = await res.json();
    if (!res.ok) {
      setFormMessage("budget-form-msg", data.error || "Failed to update budget.", "error");
      return;
    }
    setFormMessage("budget-form-msg", "Monthly budget updated.", "success");
    await fetchDashboardData();
  } catch (err) {
    setFormMessage("budget-form-msg", "Network error while saving budget.", "error");
  }
}

async function handleDeleteExpense(item) {
  const confirmed = window.confirm(
    `Delete "${item.title}" (${formatINR(item.amount)}) on ${item.date}?`
  );
  if (!confirmed) return;

  try {
    const res = await fetch(`/api/expenses/${item.id}`, { method: "DELETE" });
    if (res.ok) {
      await fetchDashboardData();
    } else {
      const data = await res.json();
      window.alert(data.error || "Could not delete expense.");
    }
  } catch (err) {
    window.alert("Network error while deleting expense.");
  }
}

function openEditModal(item) {
  document.getElementById("edit-expense-id").value = item.id;
  document.getElementById("edit-title").value = item.title;
  document.getElementById("edit-amount").value = item.amount;
  document.getElementById("edit-category").value = item.category;
  document.getElementById("edit-date").value = item.date;
  setFormMessage("edit-form-msg", "");
  document.getElementById("edit-modal").classList.remove("hidden");
}

function closeEditModal() {
  document.getElementById("edit-modal").classList.add("hidden");
}

async function handleEditExpense(event) {
  event.preventDefault();
  const id = document.getElementById("edit-expense-id").value;
  const title = document.getElementById("edit-title").value;
  const amount = document.getElementById("edit-amount").value;
  const category = document.getElementById("edit-category").value;
  const dateStr = document.getElementById("edit-date").value;

  const clientError = validateExpenseInputs(title, amount, category, dateStr);
  if (clientError) {
    setFormMessage("edit-form-msg", clientError, "error");
    return;
  }

  try {
    const res = await fetch(`/api/expenses/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: title.trim(),
        amount: Number(amount),
        category,
        date: dateStr,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      setFormMessage("edit-form-msg", data.error || "Could not update expense.", "error");
      return;
    }
    closeEditModal();
    await fetchDashboardData();
  } catch (err) {
    setFormMessage("edit-form-msg", "Network error while updating expense.", "error");
  }
}

async function handleLoadSampleData() {
  const btn = document.getElementById("sample-btn");
  btn.disabled = true;
  btn.textContent = "Loading...";
  try {
    const res = await fetch("/api/sample", { method: "POST" });
    if (res.ok) {
      await fetchDashboardData();
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Load sample data";
  }
}

function handleExportCSV() {
  const query = buildFilterQuery(false);
  window.location.href = `/api/export${query ? "?" + query : ""}`;
}

function initDashboard() {
  document.getElementById("expense-date").value = getTodayISO();
  document.getElementById("month-selector").value = getCurrentMonthValue();

  document.getElementById("expense-form").addEventListener("submit", handleAddExpense);
  document.getElementById("budget-form").addEventListener("submit", handleSaveBudget);
  document.getElementById("edit-expense-form").addEventListener("submit", handleEditExpense);
  document.getElementById("sample-btn").addEventListener("click", handleLoadSampleData);
  document.getElementById("export-csv-btn").addEventListener("click", handleExportCSV);

  document.getElementById("clear-filters-btn").addEventListener("click", () => {
    document.getElementById("filter-start").value = "";
    document.getElementById("filter-end").value = "";
    document.getElementById("filter-category").value = "All";
    fetchDashboardData();
  });

  ["filter-start", "filter-end", "filter-category", "month-selector"].forEach((id) => {
    document.getElementById(id).addEventListener("change", fetchDashboardData);
  });

  document.getElementById("close-modal-btn").addEventListener("click", closeEditModal);
  document.getElementById("cancel-edit-btn").addEventListener("click", closeEditModal);
  document.getElementById("edit-modal-backdrop").addEventListener("click", closeEditModal);

  fetchDashboardData();
}

document.addEventListener("DOMContentLoaded", initDashboard);
