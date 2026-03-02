from dateutil.relativedelta import relativedelta
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from invoices.models import Invoice


class Command(BaseCommand):
    help = "Generates and emails the VAT report for the previous month"

    def handle(self, *args, **options):
        # 1. Get the previous month and year
        last_month_date = timezone.now() - relativedelta(months=1)
        month = last_month_date.month
        year = last_month_date.year

        # 2. Query the data (Only for VAT registered invoices)
        invoices = Invoice.objects.filter(date_issued__month=month, date_issued__year=year)

        # 3. Render the LaTeX (or Text) content
        context = {
            "invoices": invoices,
            "month_name": last_month_date.strftime("%B"),
            "year": year,
            # ... add other aggregates like we did in the view ...
        }
        report_content = render_to_string("invoices/reports/vat_report.tex", context)

        # 4. Email it to you
        email = EmailMessage(
            subject=f"VAT Report - {last_month_date.strftime('%B %Y')}",
            body=f"Attached is the automated VAT report for {last_month_date.strftime('%B %Y')}.",
            from_email="billing@yourdomain.com",
            to=["your-email@example.com"],
        )

        # Attach the LaTeX source as a text file
        email.attach(f"vat_report_{year}_{month}.txt", report_content, "text/plain")
        email.send()

        self.stdout.write(self.style.SUCCESS("Successfully sent VAT report"))
