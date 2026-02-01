from django.contrib.auth import get_user_model

from invoices.models import Invoice
from invoices.utils import email_invoice_to_client, generate_invoice_pdf

user = get_user_model().objects.get(username='peter')
invoice = Invoice.objects.filter(user=user).last()

print(f"Testing PDF generation for Invoice {invoice.number}...")

try:
    pdf_bytes = generate_invoice_pdf(invoice)
    if pdf_bytes and len(pdf_bytes) > 0:
        print(f"SUCCESS: PDF generated locally ({len(pdf_bytes)} bytes).")
        
        # Now try the actual email send
        sent = email_invoice_to_client(invoice)
        if sent:
            print("SUCCESS: Email sent with attachment.")
        else:
            print("FAILURE: Email failed to send (check SMTP/Brevo settings).")
    else:
        print("FAILURE: PDF bytes are empty.")
except Exception as e:
    print(f"LATEX ERROR: {e}")