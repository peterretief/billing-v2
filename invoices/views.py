import profile
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal

from httpx import request

from .models import Invoice, InvoiceItem, VATReport, Payment
from .forms import InvoiceForm, InvoiceItemFormSet, VATPaymentForm
from .utils import generate_invoice_pdf, email_invoice_to_client
from timesheets.models import TimesheetEntry
from clients.models import Client

from django.template.loader import render_to_string

from django.conf import settings
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from timesheets.models import TimesheetEntry
from clients.models import Client

from google import genai

from django.db.models import Sum, F
from google import genai
from core.models import UserProfile

from django.utils import timezone
from datetime import date


@login_required
def record_vat_payment(request):
    if request.method == "POST":
        form = VATPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.user = request.user  # Assign to current tenant
            payment.save()
            
            # Use the manager fix we just did to get fresh numbers
            tax_summary = Invoice.objects.get_tax_summary(request.user)
            return render(request, 'invoices/partials/tax_summary_box.html', {
                'tax_summary': tax_summary,
                'message': 'Payment Recorded!'
            })
    else:
        form = VATPaymentForm(initial={'tax_type': 'VAT'})
    
    return render(request, 'invoices/partials/vat_payment_form.html', {'form': form})

@login_required
def financial_assessment(request):
    """
    Analyzes current month progress against the R 50,000 target.
    """
    today = date.today()
    start_of_month = today.replace(day=1)

    # 1. Get Actual Billed (Net) for the current month
    actual_billed = Invoice.objects.filter(
        user=request.user,
        date_issued__gte=start_of_month
    ).exclude(status='CANCELLED').aggregate(
        total=Sum('subtotal_amount')
    )['total'] or Decimal('0.00')

    # 2. Get Unbilled (WIP)
    unbilled_stats = TimesheetEntry.objects.filter(
        user=request.user, 
        is_billed=False
    ).aggregate(
        total_value=Sum(F('hours') * F('hourly_rate')),
        total_hours=Sum('hours')
    )
    total_unbilled = unbilled_stats['total_value'] or Decimal('0.00')
    total_hours = unbilled_stats['total_hours'] or 0

    # 3. Aggregated Progress
    total_progress = actual_billed + total_unbilled
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    target = user_profile.monthly_target

    # 4. Gemini Logic
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = (
        f"Context: Freelance financial health check for {today.strftime('%B %Y')}.\n"
        f"Data:\n"
        f"- Monthly Revenue Target: R {target}\n"
        f"- Already Invoiced (Net): R {actual_billed}\n"
        f"- Unbilled Work in Progress: R {total_unbilled}\n"
        f"- Total Combined Progress: R {total_progress}\n\n"
        f"Task: Assess if the user is on track for their R {target} goal. "
        f"If they are already over the target, congratulate them. Be direct (2 sentences)."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=prompt
        )
        assessment_text = response.text
    except Exception as e:
        assessment_text = "Assessment unavailable. Please check your dashboard stats."

    return render(request, 'invoices/partials/assessment_result.html', {
        'assessment': assessment_text,
        'total_unbilled': total_unbilled,
        'target': target
    })


@login_required
def bulk_post(request):
    if request.method == 'POST':
        # 1. Get the list of IDs from the checkboxes in the template
        invoice_ids = request.POST.getlist('invoice_ids')
        
        # 2. Filter: Must belong to Peter (tenant) AND be in DRAFT status
        invoices = Invoice.objects.filter(
            id__in=invoice_ids, 
            user=request.user, 
            status='DRAFT'
        )
        
        count = 0
        from .utils import email_invoice_to_client
        
        for inv in invoices:
            # Update status to PENDING (Posted)
            inv.status = 'PENDING'
            inv.save()
            
            # This is what used to work - it triggers the XeLaTeX PDF generation 
            # and sends the email to inv.client.email
            try:
                email_invoice_to_client(inv)
                count += 1
            except Exception as e:
                messages.error(request, f"Error emailing invoice {inv.number}: {str(e)}")
        
        if count > 0:
            messages.success(request, f"Successfully posted and emailed {count} invoices.")
        else:
            messages.warning(request, "No draft invoices were processed. Ensure you selected drafts.")

    return redirect('invoices:invoice_list')



@login_required
def invoice_create(request):
    # If coming from the client list, pre-fill the client
    initial_data = {}
    client_id = request.GET.get('client_id')
    if client_id:
        initial_data['client'] = get_object_or_404(Client, id=client_id, user=request.user)

    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                invoice = form.save(commit=False)
                invoice.user = request.user  # Set the tenant
                invoice.save()
                
                formset.instance = invoice
                formset.save()
                
                # Calculate totals immediately
                Invoice.objects.update_totals(invoice)
                
            messages.success(request, "Invoice created successfully.")
            return redirect('invoices:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(initial=initial_data)
        formset = InvoiceItemFormSet()

    return render(request, 'invoices/invoice_form.html', {
        'form': form,
        'formset': formset,
        'is_edit': False
    })

@login_required
def download_vat_latex(request, pk):
    """
    Downloads the raw LaTeX source code for a specific VAT Report.
    """
    report = get_object_or_404(VATReport, pk=pk, user=request.user)
    
    # Create the text-based response
    response = HttpResponse(report.latex_source, content_type='text/plain')
    
    # Format the filename: VAT_2026_01.tex
    filename = f"VAT_Report_{report.year}_{report.month:02d}.tex"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

@login_required
def resend_invoice(request, pk):
    """
    Manually triggers the email utility for an existing invoice.
    Useful for reminders or if the client lost the first one.
    """
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    # Safety Check: Don't send drafts
    if invoice.status == 'DRAFT':
        messages.warning(request, "Cannot email a DRAFT invoice. Please mark it as 'Pending/Sent' first.")
        return redirect('invoices:invoice_detail', pk=pk)

    try:
        from .utils import email_invoice_to_client
        if email_invoice_to_client(invoice):
            # Update the last_generated timestamp if you want to track activity
            invoice.last_generated = timezone.now()
            invoice.save(update_fields=['last_generated'])
            
            messages.success(request, f"Invoice #{invoice.number} has been resent to {invoice.client.email}.")
        else:
            messages.error(request, "Failed to send email. Please check your SMTP settings in settings.py.")
            
    except Exception as e:
        messages.error(request, f"Email system error: {str(e)}")

    return redirect(request.META.get('HTTP_REFERER', 'invoices:invoice_detail'))


@login_required
def generate_invoice_pdf_view(request, pk):
    """
    Fetches the invoice, ensures it belongs to the user, 
    and generates/returns the PDF response.
    """
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    try:
        # 1. Check if we need to regenerate the LaTeX source
        # (The manager clears latex_content when totals change)
        if not invoice.latex_content:
            # This is where your LaTeX utility lives
            from .utils import generate_invoice_pdf
            pdf_content = generate_invoice_pdf(invoice)
        else:
            # If we already have the PDF content/source, we use it
            from .utils import generate_invoice_pdf
            pdf_content = generate_invoice_pdf(invoice)

        # 2. Build the HTTP Response
        response = HttpResponse(pdf_content, content_type='application/pdf')
        
        # 'inline' opens in browser, 'attachment' forces download
        filename = f"Invoice_{invoice.number or invoice.pk}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response

    except Exception as e:
        messages.error(request, f"Could not generate PDF: {str(e)}")
        return redirect('invoices:invoice_detail', pk=pk)


@login_required
@transaction.atomic
def duplicate_invoice(request, pk):
    """
    Takes an existing invoice, clones it as a DRAFT, 
    and copies all its line items.
    """
    original = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    # Create the new invoice header
    new_invoice = Invoice.objects.create(
        user=request.user,
        client=original.client,
        status='DRAFT',
        tax_mode=original.tax_mode,
        billing_type=original.billing_type,
        due_date=timezone.now().date() + timedelta(days=30), # Default to 30 days from now
        # We don't copy the totals yet; the manager will sync them
    )

    # Clone the items
    for item in original.items.all():
        InvoiceItem.objects.create(
            invoice=new_invoice,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            is_taxable=item.is_taxable
        )
    
    # Run the manager math to set subtotal/tax/total
    Invoice.objects.update_totals(new_invoice)

    messages.success(request, f"Invoice duplicated as Draft #{new_invoice.id}.")
    return redirect('invoices:invoice_edit', pk=new_invoice.pk)

@login_required
def invoice_detail(request, pk):
    """View the details of a specific invoice."""
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    # This will include the related 'items' and 'payments' 
    # because of the related_names in your models.
    return render(request, 'invoices/invoice_detail.html', {
        'invoice': invoice,
    })


@login_required
def invoice_edit(request, pk):
    """Edit an existing invoice and its line items."""
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    # Safety Check: Don't allow editing if already Sent/Paid
    if invoice.status != 'DRAFT':
        messages.warning(request, "Only Draft invoices can be edited. Duplicate this invoice to make changes.")
        return redirect('invoices:invoice_detail', pk=invoice.pk)

    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                # Use your manager to recalculate tax/totals based on new items
                Invoice.objects.update_totals(invoice)
            
            messages.success(request, f"Invoice #{invoice.id} updated successfully.")
            return redirect('invoices:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)

    return render(request, 'invoices/invoice_form.html', {
        'form': form,
        'formset': formset,
        'invoice': invoice,
        'is_edit': True
    })

# --- CORE DASHBOARD & LIST VIEWS ---

@login_required
def dashboard(request):
    # 1. Basic Querysets
    invoices = Invoice.objects.filter(user=request.user)
    vat_reports = VATReport.objects.filter(user=request.user).order_by('-year', '-month')
    
    # 2. Calculate Unbilled WIP (Work in Progress)
    # This sums up all logged timesheets that have NOT been billed yet
    unbilled_data = TimesheetEntry.objects.filter(
        user=request.user, 
        is_billed=False
    ).aggregate(
        total_value=Sum(F('hours') * F('hourly_rate'))
    )
    unbilled_value = unbilled_data['total_value'] or Decimal('0.00')

    # 3. Aggregated Invoice Stats
    stats = invoices.aggregate(
        billed=Sum('total_amount'),
        tax=Sum('tax_amount'),
        paid=Sum('payments__amount')  
    )
    
    billed = stats['billed'] or Decimal('0.00')
    tax = stats['tax'] or Decimal('0.00')
    
    # 4. Use Manager methods for specialized reports
    tax_summary = Invoice.objects.get_tax_summary(request.user)
    tax_year_stats = Invoice.objects.get_tax_year_report(request.user)
    outstanding = Invoice.objects.get_total_outstanding(request.user)

    context = {
        'unbilled_value': unbilled_value,  # THIS FIXES THE R 0.00 ISSUE
        'total_billed': billed,
        'total_tax': tax,
        'total_outstanding': outstanding,
        'tax_year': tax_year_stats,
        'tax_summary': tax_summary,
        'vat_reports': vat_reports, 
        'recent_invoices': invoices.order_by('-date_issued', '-id')[:5],
    }
    return render(request, 'invoices/dashboard.html', context)


@login_required
def invoice_list(request):
    # Corrected: Use date_issued instead of date
    invoice_queryset = Invoice.objects.filter(user=request.user).select_related('client').order_by('-date_issued', '-id')
    
    status_filter = request.GET.get('status')
    if status_filter == 'UNPAID':
        invoice_queryset = invoice_queryset.exclude(status='PAID')

    paginator = Paginator(invoice_queryset, 10) 
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'invoices/invoice_list.html', {'invoices': page_obj})

# --- INVOICE ACTION VIEWS ---



@login_required
def record_payment(request, pk):
    if request.method == 'POST':
        invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
        amount = Decimal(request.POST.get('amount', '0'))

        if amount > 0:
            # 1. Auto-Post Logic
            if invoice.status == 'DRAFT':
                invoice.status = 'SENT' # Or 'POSTED' based on your status choices
                # If you have a method to generate the invoice number on post, call it here
                if not invoice.number:
                    invoice.generate_number() 
                invoice.save()
            
            # 2. Record the payment
            Payment.objects.create(
                invoice=invoice,
                amount=amount,
                reference=request.POST.get('reference', 'Payment received')
            )

            # 3. Final Status Check
            # Re-fetch or calculate to see if it's now fully paid
            if invoice.balance_due <= 0:
                invoice.status = 'PAID'
                invoice.save()

            messages.success(request, f"Invoice #{invoice.number} updated and payment recorded.")
            
    return redirect(request.META.get('HTTP_REFERER', 'invoices:dashboard'))


@login_required
def mark_invoice_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    balance = invoice.balance_due
    
    if balance > 0:
        with transaction.atomic():
            Payment.objects.create(
                user=request.user,
                invoice=invoice,
                amount=balance,
                reference="Marked Paid (Full)"
            )
            invoice.status = 'PAID'
            invoice.save()
        messages.success(request, f"Invoice #{invoice.id} fully settled.")
    return redirect(request.META.get('HTTP_REFERER', 'invoices:dashboard'))

# ... [Duplicate, PDF, and resend views remain the same, just ensure they use date_issued if needed] ...

@login_required
def generate_vat_report(request):
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))
    
    # Corrected: Use date_issued__month and date_issued__year
    invoices = Invoice.objects.filter(
        user=request.user, 
        date_issued__month=month, 
        date_issued__year=year
    )
    totals = invoices.aggregate(net=Sum('subtotal_amount'), vat=Sum('tax_amount'))
    
    context = {
        'invoices': invoices,
        'month_name': timezone.datetime(year, month, 1).strftime('%B'),
        'year': year,
        'net_total': totals['net'] or 0,
        'vat_total': totals['vat'] or 0,
    }
    
    latex_content = render_to_string('invoices/reports/vat_report.tex', context)
    
    VATReport.objects.update_or_create(
        user=request.user, month=month, year=year,
        defaults={
            'latex_source': latex_content, 
            'net_total': totals['net'] or 0, 
            'vat_total': totals['vat'] or 0
        }
    )
    
    messages.success(request, f"VAT Report for {month}/{year} generated.")
    return redirect('invoices:dashboard')