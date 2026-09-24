import sys
import io
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("sandbox_runner")


class LandedCostCalculationResult(BaseModel):
    original_amount: float
    original_currency: str
    exchange_rate: float
    amount_usd: float
    tax_rate: float
    tax_amount_usd: float
    shipping_duties_usd: float
    total_landed_cost_usd: float
    execution_logs: str


class LandedCostSandboxRunner:
    """
    Safe Python Code Execution Sandbox for financial calculations:
    Converts multi-currency purchase orders (EUR, GBP, JPY, CAD) to USD,
    applies tax rates and shipping/duties, and computes total landed cost in USD.
    """

    EXCHANGE_RATES = {
        "USD": 1.0,
        "EUR": 1.08,    # 1 EUR = $1.08 USD
        "GBP": 1.30,    # 1 GBP = $1.30 USD
        "JPY": 0.0068,  # 1 JPY = $0.0068 USD
        "CAD": 0.74     # 1 CAD = $0.74 USD
    }

    @classmethod
    def execute_landed_cost_calc(
        cls,
        amount: float,
        currency: str = "USD",
        tax_rate: float = 0.0,
        shipping_duties: float = 0.0
    ) -> LandedCostCalculationResult:
        """
        Executes Python calculation in a isolated namespace capturing stdout logs.
        """
        currency_clean = (currency or "USD").upper()
        fx_rate = cls.EXCHANGE_RATES.get(currency_clean, 1.0)

        sandbox_code = f"""
# Python Financial Sandbox Calculation
amount = {amount}
currency = '{currency_clean}'
fx_rate = {fx_rate}
tax_rate = {tax_rate}
shipping_duties = {shipping_duties}

amount_usd = amount * fx_rate
tax_amount_usd = amount_usd * tax_rate
total_landed_cost_usd = amount_usd + tax_amount_usd + shipping_duties

print(f"Original: {{amount}} {{currency}} @ FX {{fx_rate}}")
print(f"Base USD: ${{amount_usd:,.2f}}")
print(f"Tax ({{tax_rate*100}}%): ${{tax_amount_usd:,.2f}}")
print(f"Shipping/Duties: ${{shipping_duties:,.2f}}")
print(f"Total Landed Cost USD: ${{total_landed_cost_usd:,.2f}}")
"""

        log_buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = log_buffer

        local_vars: Dict[str, Any] = {}
        safe_builtins = {"print": print, "float": float, "round": round, "abs": abs, "str": str, "int": int}
        try:
            exec(sandbox_code, {"__builtins__": safe_builtins}, local_vars)
        finally:
            sys.stdout = old_stdout


        logs = log_buffer.getvalue().strip()

        return LandedCostCalculationResult(
            original_amount=amount,
            original_currency=currency_clean,
            exchange_rate=fx_rate,
            amount_usd=round(local_vars["amount_usd"], 2),
            tax_rate=tax_rate,
            tax_amount_usd=round(local_vars["tax_amount_usd"], 2),
            shipping_duties_usd=round(shipping_duties, 2),
            total_landed_cost_usd=round(local_vars["total_landed_cost_usd"], 2),
            execution_logs=logs
        )


sandbox_runner = LandedCostSandboxRunner()
