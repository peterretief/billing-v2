import os
import subprocess
import shutil
from tempfile import TemporaryDirectory
from decimal import Decimal

from django.conf import settings
from django.template.loader import render_to_string

def tex_safe(text):
    """
    Escapes LaTeX special characters so they don't crash the compiler.
    """
    if text is None:
        return ""
    text = str(text)
    mapping = {
        '&': r'\&',
        '$': r'\$',
        '%': r'\%',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    return "".join(mapping.get(c, c) for c in text)

def generate_invoice_pdf(invoice):
    # Access the profile from the custom User model
    profile = invoice.user.profile
    
    # 1. Basic Header Context
    context = {
        'company_name': tex_safe(profile.company_name),
        'vat_number': tex_safe(profile.vat_number),
        'tax_number': tex_safe(profile.tax_number),
        'vendor_number': tex_safe(profile.vendor_number),
        'invoice_number': tex_safe(invoice.number),
        'date_issued': tex_safe(invoice.date_issued),
        'due_date': tex_safe(invoice.due_date),
        'client_name': tex_safe(invoice.client.name),
        'bank_name': tex_safe(profile.bank_name),
        'account_holder': tex_safe(profile.account_holder),
        'account_number': tex_safe(profile.account_number),
        'branch_code': tex_safe(profile.branch_code),
    }

    # Billing Mode Setup (Service vs Product)
    is_service = invoice.billing_type == 'service'
    context['label_qty'] = "Hours" if is_service else "Qty"
    context['label_rate'] = "Rate" if is_service else "Unit Price"

    # Address Handling
    context['profile_address_safe'] = tex_safe(profile.address).replace('\n', r' \\ ')
    context['client_address_safe'] = tex_safe(invoice.client.address).replace('\n', r' \\ ')

    # 2. Financial Calculations with Tax Exempt Logic
    subtotal = sum(item.quantity * item.unit_price for item in invoice.items.all())
    
    # Logic: If tax_exempt is checked on the invoice, rate is 0. 
    # Otherwise, use the rate from the user profile.
    if getattr(invoice, 'tax_exempt', False):
        tax_perc = Decimal('0.00')
        context['tax_display_label'] = "VAT Exempt"
    else:
        tax_perc = profile.tax_rate if profile.tax_rate is not None else Decimal('15.00')
        context['tax_display_label'] = f"VAT ({tax_perc:.0f}%)"

    vat_total = subtotal * (tax_perc / Decimal('100.0'))
    grand_total = subtotal + vat_total

    # Formatting Totals for the PDF (Fixed format strings)
    context['subtotal'] = f"{subtotal:,.2f}"
    context['vat_total'] = f"{vat_total:,.2f}"
    context['grand_total'] = f"{grand_total:,.2f}"

    # 3. Handle Items List
    context['items'] = [
        {
            'description': tex_safe(item.description),
            'quantity': f"{item.quantity:.2f}" if is_service else f"{item.quantity:.0f}",
            'unit_price': f"{item.unit_price:,.2f}",
            'total': f"{(item.quantity * item.unit_price):,.2f}"
        } for item in invoice.items.all()
    ]

    # 4. Render and Compile
    latex_content = render_to_string('invoices/latex/invoice_template.tex', context)

    with TemporaryDirectory() as tempdir:
        tex_file_path = os.path.join(tempdir, 'invoice.tex')
        with open(tex_file_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)

        # Run xelatex
        result = subprocess.run(
            ['xelatex', '-interaction=nonstopmode', '-output-directory', tempdir, tex_file_path],
            capture_output=True,
            text=True,
            timeout=30
        )

        pdf_path = os.path.join(tempdir, 'invoice.pdf')
        if os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                return f.read()
        else:
            # If LaTeX fails, this helps you see why in the logs
            raise Exception(f"LaTeX Error: {result.stdout}")