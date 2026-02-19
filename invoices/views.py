from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Sum
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

# AI Integration
from google import genai

from clients.models import Client
from core.decorators import setup_required
from core.models import BillingAuditLog, UserProfile
from items.models import Item
from timesheets.models import TimesheetEntry

from .forms import InvoiceForm, VATPaymentForm

from django.db.models import Prefetch
from invoices.models import Invoice, InvoiceEmailStatusLog

# Local Apps
from .models import Invoice, Payment, VATReport
from .utils import email_invoice_to_client, generate_invoice_pdf

# --- FORMSET DEFINITION ---
InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    Item,
    fields=('description', 'quantity', 'unit_price', 'is_taxable'),
    extra=1,
    can_delete=True
)


@login_required
@setup_required
def get_payment_modal(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    return render(request, 'invoices/partials/payment_modal_content.html', {'invoice': invoice})


@login_required
@setup_required  # This ensures they can't see stats until setup is done
def dashboard(request):
    """Main overview for the business owner."""
    if request.user.is_ops:
        # Ops users see data of users they added, plus their own
        users_to_show = list(request.user.added_users.all()) + [request.user]
        invoices = Invoice.objects.filter(user__in=users_to_show).select_related('client')
        unbilled_ts = TimesheetEntry.objects.filter(user__in=users_to_show, is_billed=False).aggregate(
            total_value=Sum(F('hours') * F('hourly_rate')),
        )
        unbilled_items = Item.objects.filter(user__in=users_to_show, is_billed=False).aggregate(
            total_value=Sum(F('quantity') * F('unit_price'))
        )
        flagged_count = BillingAuditLog.objects.filter(
            user__in=users_to_show,
            is_anomaly=True
        ).exclude(invoice__status='PAID').count()
    else:
        # Regular users see their own data
        invoices = Invoice.objects.filter(user=request.user).select_related('client')
        unbilled_ts = TimesheetEntry.objects.filter(user=request.user, is_billed=False).aggregate(
            total_value=Sum(F('hours') * F('hourly_rate')),
        )
        unbilled_items = Item.objects.filter(user=request.user, is_billed=False).aggregate(
            total_value=Sum(F('quantity') * F('unit_price'))
        )
        flagged_count = BillingAuditLog.objects.filter(
            user=request.user,
            is_anomaly=True
        ).exclude(invoice__status='PAID').count()

    stats = invoices.aggregate(
        billed=Sum('total_amount'),
        paid=Sum('payments__amount')  
    )
    
    total_outstanding = Invoice.objects.get_total_outstanding(request.user)

    context = {
        'unbilled_value': (unbilled_ts['total_value'] or Decimal('0.00')) + (unbilled_items['total_value'] or Decimal('0.00')),
        'total_billed': stats['billed'] or Decimal('0.00'),
        'total_outstanding': total_outstanding,
        'tax_summary': Invoice.objects.get_tax_summary(request.user),
        
        # This table shows the 5 most recent invoices regardless of status
        'recent_invoices': invoices.order_by('-date_issued', '-id')[:5],
        'flagged_count': flagged_count,
        
        # This is for your "Dispatched & Emailed" history section
        'sent_history': invoices.filter(is_emailed=True).order_by('-emailed_at')[:10],
    }

    return render(request, 'invoices/dashboard.html', context)


@login_required
@setup_required
def invoice_list(request):
    invoice_queryset = Invoice.objects.filter(
        user=request.user
    ).select_related('client').prefetch_related(
        Prefetch(
            'delivery_logs',  # ← matches your model
            queryset=InvoiceEmailStatusLog.objects.order_by('-created_at'),
        )
    ).order_by('-date_issued', '-id')

    status_filter = request.GET.get('status')
    if status_filter == 'UNPAID':
        invoice_queryset = invoice_queryset.exclude(status='PAID')

    paginator = Paginator(invoice_queryset, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'invoices/invoice_list.html', {'invoices': page_obj})


@login_required
@setup_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    return render(request, 'invoices/invoice_detail.html', {'invoice': invoice})

@login_required
@setup_required
def invoice_create(request):
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
                invoice.user = request.user
                invoice.save()
                formset.instance = invoice
                formset.save()
                Invoice.objects.update_totals(invoice)
            messages.success(request, "Invoice created.")
            return redirect('invoices:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(initial=initial_data)
        formset = InvoiceItemFormSet()
    return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset, 'is_edit': False})

@login_required
@setup_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if invoice.status != 'DRAFT':
        messages.warning(request, "Only Draft invoices can be edited.")
        return redirect('invoices:invoice_detail', pk=invoice.pk)

    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
                Invoice.objects.update_totals(invoice)
            return redirect('invoices:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)
    return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset, 'is_edit': True})

@login_required
@setup_required
def duplicate_invoice(request, pk):
    original = get_object_or_404(Invoice, pk=pk, user=request.user)
    with transaction.atomic():
        new_invoice = Invoice.objects.create(
            user=request.user, client=original.client, status='DRAFT',
            tax_mode=original.tax_mode, billing_type=original.billing_type,
            due_date=timezone.now().date() + timedelta(days=30)
        )
        for item in original.billed_items.all():
            Item.objects.create(
                user=request.user, client=original.client, invoice=new_invoice,
                description=item.description, quantity=item.quantity,
                unit_price=item.unit_price, is_taxable=item.is_taxable, is_billed=False
            )
        Invoice.objects.update_totals(new_invoice)
    messages.success(request, f"Duplicated as Draft #{new_invoice.id}")
    return redirect('invoices:invoice_edit', pk=new_invoice.pk)

@login_required
@setup_required
def bulk_post(request):
    if request.method == 'POST':
        invoice_ids = request.POST.getlist('invoice_ids')
        invoices = Invoice.objects.filter(id__in=invoice_ids, user=request.user, status='DRAFT')
        count = 0
        for inv in invoices:
            with transaction.atomic():
                inv.status = 'PENDING'
                inv.save()
                inv.billed_items.all().update(is_billed=True)
                item_desc = inv.billed_items.values_list('description', flat=True)
                Item.objects.filter(user=request.user, client=inv.client, is_recurring=True,
                                     description__in=item_desc).update(last_billed_date=timezone.now().date())
                try:
                    if email_invoice_to_client(inv): count += 1
                except Exception: pass
        messages.success(request, f"Processed {count} invoices.")
    return redirect('invoices:invoice_list')

@login_required
@setup_required
def mark_invoice_paid(request, pk):
    """Settle an invoice fully by creating a Payment record."""
    if request.method != "POST":
        return redirect('invoices:invoice_detail', pk=pk)

    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    balance = invoice.balance_due

    if balance > 0:
        try:
            with transaction.atomic():
                # FIX: Match the fields in your Payment model exactly
                Payment.objects.create(
                    user=request.user,  # <--- This is the missing piece!
                    invoice=invoice, 
                    amount=balance, 
                    reference="Marked Paid (Full)"
                )
                # Note: Your model's save() method will auto-update 
                # invoice status to 'PAID' if balance is 0.
            messages.success(request, f"Invoice #{invoice.number} settled.")
        except Exception as e:
            messages.error(request, f"Payment error: {str(e)}")
            
    return redirect(request.META.get('HTTP_REFERER', 'invoices:dashboard'))



@login_required
@setup_required
def record_payment(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    next_url = request.META.get('HTTP_REFERER') or reverse('invoices:dashboard')

    if request.method == 'POST':
        try:
            amount_str = request.POST.get('amount', '0').replace(',', '').strip()
            amount = Decimal(amount_str)
            
            with transaction.atomic():
                Payment.objects.create(
                    user=request.user,
                    invoice=invoice,
                    amount=amount,
                    reference=request.POST.get('reference', 'Manual Payment')
                )
                invoice.save()
            
            messages.success(request, f"Payment of {amount} recorded.")
            
            # --- HTMX REDIRECT FIX ---
            if request.headers.get('HX-Request'):
                response = HttpResponse(status=204) # No Content
                response['HX-Redirect'] = next_url
                return response
            # -------------------------
            
            return redirect(next_url)

        except ValidationError as e:
            messages.error(request, f"Error: {', '.join(e.messages)}")
        except (InvalidOperation, ValueError):
            messages.error(request, "Invalid numeric amount.")

    return redirect(next_url)

"""
@login_required
def record_payment(request, pk):
    if request.method == 'POST':
        invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
        try:
            amount_str = request.POST.get('amount', '0').replace(',', '')
            amount = Decimal(amount_str)
            
            if amount > 0:
                with transaction.atomic():
                    Payment.objects.create(
                        user=request.user,  # <--- This is the missing piece!
                        invoice=invoice, 
                        amount=amount, 
                        reference=request.POST.get('reference', 'Manual Payment')
                    )
                messages.success(request, f"Payment of R {amount} recorded.")
        except Exception as e:
            messages.error(request, f"Error recording payment: {str(e)}")
            
    return redirect(request.META.get('HTTP_REFERER', 'invoices:dashboard'))
"""


@login_required
@setup_required
def generate_invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    requested_style = request.GET.get('style', 'default')
    template_name = 'invoice_modern.tex' if requested_style == 'modern' else 'invoice_template.tex'
    try:
        pdf_content = generate_invoice_pdf(invoice, template_name=template_name)
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Invoice_{invoice.pk}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"PDF Error: {str(e)}")
        return redirect('invoices:invoice_detail', pk=pk)

@login_required
@setup_required
def resend_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if invoice.status == 'DRAFT':
        messages.warning(request, "Cannot email a draft.")
    else:
        if email_invoice_to_client(invoice):
            messages.success(request, "Invoice resent.")
    return redirect(request.META.get('HTTP_REFERER', 'invoices:invoice_detail'))

@login_required
def financial_assessment(request):
    today = date.today()
    start_of_month = today.replace(day=1)
    actual_billed = Invoice.objects.filter(user=request.user, date_issued__gte=start_of_month).exclude(status='CANCELLED').aggregate(total=Sum('subtotal_amount'))['total'] or Decimal('0.00')
    unbilled_qs = TimesheetEntry.objects.filter(user=request.user, is_billed=False)
    total_unbilled = unbilled_qs.aggregate(val=Sum(F('hours') * F('hourly_rate')))['val'] or Decimal('0.00')
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    target = user_profile.monthly_target or Decimal('50000.00')
    
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    currency = user_profile.currency
    prompt = f"Target: {currency} {target}. Invoiced: {currency} {actual_billed}. WIP: {currency} {total_unbilled}. Assess in 2 sentences."
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        assessment_text = response.text
    except:
        assessment_text = "Assessment unavailable."
    return render(request, 'invoices/partials/assessment_result.html', {'assessment': assessment_text, 'target': target, 'total_progress': actual_billed + total_unbilled})

@login_required
def record_vat_payment(request):
    if request.method == "POST":
        form = VATPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.user = request.user
            payment.save()
            return render(request, 'invoices/partials/tax_summary_box.html', {'tax_summary': Invoice.objects.get_tax_summary(request.user)})
    return render(request, 'invoices/partials/vat_payment_form.html', {'form': VATPaymentForm(initial={'tax_type': 'VAT'})})

@login_required
def generate_vat_report(request):
    month = int(request.GET.get('month', timezone.now().month))
    year = int(request.GET.get('year', timezone.now().year))
    invoices = Invoice.objects.filter(user=request.user, date_issued__month=month, date_issued__year=year)
    totals = invoices.aggregate(net=Sum('subtotal_amount'), vat=Sum('tax_amount'))
    VATReport.objects.update_or_create(user=request.user, month=month, year=year, defaults={'net_total': totals['net'] or 0, 'vat_total': totals['vat'] or 0})
    messages.success(request, "Report generated.")
    return redirect('invoices:dashboard')

@login_required
def download_vat_latex(request, pk):
    """Downloads raw LaTeX source for a VAT Report."""
    report = get_object_or_404(VATReport, pk=pk, user=request.user)
    response = HttpResponse(report.latex_source, content_type='text/plain')
    filename = f"VAT_Report_{report.year}_{report.month:02d}.tex"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def delete_invoice(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if invoice.status != 'DRAFT':
        messages.error(request, "Only drafts can be deleted.")
        return redirect('invoices:invoice_detail', pk=pk)
    if request.method == 'POST':
        invoice.delete()
        return redirect('invoices:invoice_list')
    return render(request, 'invoices/invoice_confirm_delete.html', {'invoice': invoice})


@login_required
def billing_audit_report(request):
    """
    Provides a high-level summary of AI performance and billing volume.
    """
    # Get all logs for the current user
    logs = BillingAuditLog.objects.filter(user=request.user).order_by('-created_at')
    
    # 1. AI Catch Rate
    total_logs = logs.count()
    anomalies_caught = logs.filter(is_anomaly=True).count()
    catch_rate = (anomalies_caught / total_logs * 100) if total_logs > 0 else 0
    
    # 2. Financial Impact (Value of caught anomalies)
    # Note: We extract the total from the JSON details field
    anomaly_details = logs.filter(is_anomaly=True).values_list('details', flat=True)
    potential_errors_value = sum([Decimal(str(d.get('total', 0))) for d in anomaly_details])

    # 3. Success vs. Intervention
    # Draft = Intervened, Pending/Paid = Successful
    success_count = logs.filter(invoice__status__in=['PENDING', 'PAID']).count()

    context = {
        'total_logs': total_logs,
        'anomalies_caught': anomalies_caught,
        'catch_rate': round(catch_rate, 1),
        'potential_errors_value': potential_errors_value,
        'success_count': success_count,
        'recent_logs': logs[:20],  # Show last 20 events
    }
    return render(request, 'invoices/audit_report.html', context)