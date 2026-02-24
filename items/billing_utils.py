# items/billing_utils.py


def email_item_invoice_to_client(invoice):
    try:
        # Fix 1: Ensure we refresh the relationship before rendering
        invoice.refresh_from_db()
        pdf_bytes = generate_invoice_pdf(invoice)

        # ... setup email as usual ...

        # Fix 2: REMOVE the .tex attachment line that Brevo hates
        # email.attach(f"Invoice_{invoice.number}.tex", ...)

        # Keep only the PDF
        email.attach(f"Invoice_{invoice.number}.pdf", pdf_bytes, "application/pdf")

        email.send()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False
