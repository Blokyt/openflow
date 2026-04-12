"""Forecasting API module for OpenFlow."""
from datetime import date
from pathlib import Path
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter

from backend.core.config import load_config
from backend.core.database import get_conn

router = APIRouter()

CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"


@router.get("/projection")
def get_projection(months: int = 6):
    """Compute cash-flow projection for the next N months.

    Logic:
    1. Compute current balance from reference amount + transactions sum since reference date.
    2. Compute average monthly income and expenses from the last 6 months of transactions.
    3. Project forward: for each future month, balance += avg_income - avg_expenses.
    """
    # --- Load config for balance reference ---
    try:
        config = load_config(str(CONFIG_PATH))
        reference_amount = config.balance.amount
        reference_date = config.balance.date
    except Exception:
        reference_amount = 0.0
        reference_date = None

    conn = get_conn()
    try:
        # --- Step 1: current balance ---
        if reference_date:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE date >= ?",
                (reference_date,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions"
            ).fetchone()
        transactions_sum = row[0]
        current_balance = reference_amount + transactions_sum

        # --- Step 2: averages over the last 6 calendar months ---
        today = date.today()
        # Start of the window: first day of the month 6 months ago
        window_start = (today.replace(day=1) - relativedelta(months=6)).isoformat()
        # End of the window: yesterday (we don't include the current partial month)
        window_end = today.isoformat()

        income_row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0)
               FROM transactions
               WHERE amount > 0 AND date >= ? AND date < ?""",
            (window_start, window_end),
        ).fetchone()
        expenses_row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0)
               FROM transactions
               WHERE amount < 0 AND date >= ? AND date < ?""",
            (window_start, window_end),
        ).fetchone()

        total_income = income_row[0]
        total_expenses = abs(expenses_row[0])  # store as positive number

        avg_monthly_income = total_income / 6
        avg_monthly_expenses = total_expenses / 6

        # --- Step 3: project forward ---
        projection = []
        running_balance = current_balance
        for i in range(1, months + 1):
            future_month = today.replace(day=1) + relativedelta(months=i)
            month_label = future_month.strftime("%Y-%m")
            running_balance = running_balance + avg_monthly_income - avg_monthly_expenses
            projection.append({
                "month": month_label,
                "projected_balance": round(running_balance, 2),
            })

        return {
            "current_balance": round(current_balance, 2),
            "avg_monthly_income": round(avg_monthly_income, 2),
            "avg_monthly_expenses": round(avg_monthly_expenses, 2),
            "projection": projection,
        }
    finally:
        conn.close()
