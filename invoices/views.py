from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator

from .models import Invoice, InvoiceItem
from .forms import InvoiceForm, InvoiceItemFormSet
from .utils import generate_invoice_pdf

# invoices/views.py
from django.shortcuts import redirect, get_object_or_404
from .models import Invoice, Payment

from .utils import email_invoice_to_client # Import the function we built

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from django.db import transaction

@login_required
def mark_invoice_paid_full(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    # Only process if there is actually money owed
    if invoice.balance_due > 0:
        with transaction.atomic():
            # Create a payment record to balance the books
            Payment.objects.create(
                invoice=invoice,
                amount=invoice.balance_due,
                reference="Full Payment (Quick Action)",
                date_paid=timezone.now().date()
            )
            
            # Update status
            invoice.status = Invoice.Status.PAID
            invoice.save()
            
        messages.success(request, f"Invoice {invoice.number} marked as fully paid.")
    else:
        messages.info(request, "This invoice is already settled.")
        
    return redirect('invoices:invoice_list')

@login_required
def record_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if request.method == 'POST':
        amount = request.POST.get('amount')
        Payment.objects.create(
            invoice=invoice,
            amount=amount,
            reference=request.POST.get('reference', '')
        )
        # Update status if fully paid
        if invoice.balance_due <= 0:
            invoice.status = 'PAID'
            invoice.save()
        
        messages.success(request, f"Payment of R {amount} recorded.")
    return redirect('invoices:invoice_detail', pk=invoice.pk)


@login_required
def duplicate_invoice(request, pk):
    original_invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    with transaction.atomic():
        # 1. Create the new Invoice object
        new_invoice = Invoice.objects.create(
            user=request.user,
            client=original_invoice.client,
            status='DRAFT',  # Always start as draft
            date_issued=timezone.now().date(),
            due_date=timezone.now().date() + timedelta(days=14),
            # Leave invoice_number empty if your model auto-generates it on post
        )
        
        # 2. Duplicate the line items
        for item in original_invoice.items.all():
            InvoiceItem.objects.create(
                invoice=new_invoice,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                is_taxable=item.is_taxable
            )
            
    messages.success(request, f"Invoice duplicated. New Draft: #{new_invoice.id}")
    return redirect('invoices:invoice_edit', pk=new_invoice.pk)


# invoices/views.py
@login_required
def bulk_post_invoices(request):
    if request.method == 'POST':
        invoice_ids = request.POST.getlist('invoice_ids')
        invoices = Invoice.objects.filter(
            id__in=invoice_ids, 
            user=request.user, 
            status='DRAFT'
        )
        
        count = 0
        for inv in invoices:
            inv.status = 'PENDING'
            inv.save()
            # This triggers your xelatex PDF and dummy email
            email_invoice_to_client(inv) 
            count += 1
            
        messages.success(request, f"Successfully posted and emailed {count} invoices.")
    return redirect('invoices:invoice_list')


@login_required
def resend_invoice(request, pk):
    # Only allow the owner of the invoice to resend it
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    # We only resend if it's already been 'posted' (PENDING or PAID)
    # This prevents accidentally sending out DRAFTS
    if invoice.status != 'DRAFT':
        success = email_invoice_to_client(invoice)
        if success:
            messages.success(request, f"Invoice {invoice.number} has been resent to {invoice.client.email}.")
        else:
            messages.error(request, "Failed to resend the email. Check your logs.")
    else:
        messages.warning(request, "You cannot send a Draft. Please Post the invoice first.")

    return redirect(request.META.get('HTTP_REFERER', 'invoices:invoice_list'))


@login_required
def mark_status(request, pk, new_status):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    old_status = invoice.status
    
    if new_status in [s[0] for s in Invoice.Status.choices]:
        # 1. Update the status
        invoice.status = new_status
        invoice.save(update_fields=['status'])
        
        # 2. Trigger the dummy email if transitioning to PENDING
        if old_status == 'DRAFT' and new_status == 'PENDING':
            # This calls your generate_invoice_pdf logic internally
            email_invoice_to_client(invoice)
            messages.success(request, "Invoice posted! Check your terminal for the email output.")
        else:
            messages.success(request, f"Status updated to {new_status}.")
            
    return redirect(request.META.get('HTTP_REFERER', 'invoices:invoice_list'))

@login_required
def mark_invoice_paid(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    invoice.status = 'PAID'
    invoice.save(update_fields=['status'])
    
    # Send them back to wherever they came from (Client Detail or Dashboard)
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))



from django.db.models import Sum
from .models import Invoice

@login_required
def dashboard(request):
    invoices = Invoice.objects.filter(user=request.user)
    
    # 1. Sum up the physical columns we have on the Invoice model
    stats = invoices.aggregate(
        billed=Sum('total_amount'),
        tax=Sum('tax_amount')
    )
    
    # 2. Sum up all payments linked to these invoices
    # We follow the relationship from Invoice -> Payments
    total_paid = invoices.aggregate(
        paid=Sum('payments__amount')
    )['paid'] or 0

    # 3. Calculate the totals for the context
    billed = stats['billed'] or 0
    tax = stats['tax'] or 0
    outstanding = billed - total_paid

    context = {
        'total_billed': billed,
        'total_tax': tax,
        'total_outstanding': outstanding,
        'recent_invoices': invoices.order_by('-date_issued')[:5],
    }
    return render(request, 'invoices/dashboard.html', context)

@login_required
def invoice_list(request):
    stats = Invoice.objects.get_dashboard_stats(request.user)
    invoice_queryset = Invoice.objects.filter(user=request.user).order_by('-date_issued', '-id')
    
    paginator = Paginator(invoice_queryset, 10) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'invoices/invoice_list.html', {
        'invoices': page_obj,
        'stats': stats
    })

@login_required
def invoice_create(request):
    client_id = request.GET.get('client_id')
    initial_data = {'client': client_id} if client_id else {}

    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.user = request.user
            invoice.latex_content = "" # Clear cache
            invoice.save()
            
            formset.instance = invoice
            formset.save()
            
            # Recalculate totals immediately
            Invoice.objects.update_totals(invoice)
            
            messages.success(request, f"Invoice {invoice.number or 'Draft'} created.")
            return redirect('invoices:invoice_list')
    else:
        form = InvoiceForm(initial=initial_data)
        formset = InvoiceItemFormSet()

    return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset, 'is_edit': False})

@login_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)
        
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.latex_content = "" # Clear old PDF source
            invoice.save()
            
            formset.save()
            
            # Recalculate totals
            Invoice.objects.update_totals(invoice)
            
            messages.success(request, f"Invoice {invoice.number} updated.")
            return redirect('invoices:invoice_list')
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)
    
    return render(request, 'invoices/invoice_form.html', {
        'form': form, 
        'formset': formset, 
        'invoice': invoice, 
        'is_edit': True
    })

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    return render(request, 'invoices/invoice_detail.html', {'invoice': invoice})

@login_required
def generate_invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    try:
        pdf_content = generate_invoice_pdf(invoice)
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Invoice_{invoice.number}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect('invoices:invoice_detail', pk=pk)
    

import os
import subprocess
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string
from django.db.models import Sum
from decimal import Decimal

@login_required
def export_vat_report(request):
    # Default to current month if not specified
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))
    
    invoices = Invoice.objects.filter(
        user=request.user,
        date_issued__month=month,
        date_issued__year=year,
        tax_mode=Invoice.TaxMode.FULL
    ).select_related('client')

    # Aggregates for the report header
    totals = invoices.aggregate(
        net=Sum('subtotal_amount'),
        vat=Sum('tax_amount'),
        gross=Sum('total_amount')
    )

    context = {
        'invoices': invoices,
        'month_name': timezone.datetime(year, month, 1).strftime('%B'),
        'year': year,
        'profile': request.user.profile,
        'net_total': totals['net'] or 0,
        'vat_total': totals['vat'] or 0,
        'gross_total': totals['gross'] or 0,
    }

    # Render LaTeX
    latex_content = render_to_string('invoices/reports/vat_report.tex', context)
    
    # Save as text file for audit trail
    file_path = os.path.join(settings.MEDIA_ROOT, f'vat_report_{year}_{month}.txt')
    with open(file_path, 'w') as f:
        f.write(latex_content)

    # Return as PDF (Reuse your existing PDF generation logic here)
    # ... (code to run pdflatex) ...
    return HttpResponse(latex_content, content_type='text/plain') # For now, view the code   