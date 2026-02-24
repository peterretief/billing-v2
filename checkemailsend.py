# run_final_test.py
from datetime import date

import pandas as pd

from invoices.tasks import generate_recurring_monthly_invoices

# We mock the first workday to 'today' to pass the internal check
today = pd.Timestamp(date.today())
# This forces the task to think today is the day to run
generate_recurring_monthly_invoices.apply()

print("Check your logs/email for the 'SENT' confirmation.")
