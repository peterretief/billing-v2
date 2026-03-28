from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from invoices.models import Invoice, InvoiceEmailStatusLog
from .models import Item

@login_required
def item_invoice_email_log(request, item_id):
    """
    Shows a log of all invoices generated and emailed for a specific recurring item.
    Enhanced debug info for troubleshooting.
    UI improvement: fallback to show all invoices for the same client/description if no direct logs found.
    """
    item = get_object_or_404(Item, pk=item_id, user=request.user)
    invoices = Invoice.objects.filter(billed_items__id=item.id).distinct().order_by('-date_issued')
    invoice_logs = []
    debug_invoice_ids = []
    debug_log_counts = []
    debug_log_details = []
    for invoice in invoices:
        logs = list(invoice.delivery_logs.all().order_by('-created_at'))
        invoice_logs.append({
            'invoice': invoice,
            'logs': logs,
        })
        debug_invoice_ids.append(invoice.id)
        debug_log_counts.append(len(logs))
        debug_log_details.append([
            {'log_id': log.id, 'status': log.status, 'created_at': log.created_at.isoformat()} for log in logs
        ])

    # Fallback: If no invoices found, try to find all invoices for this client/description
    fallback_invoices = []
    if not invoice_logs:
        fallback_invoices = Invoice.objects.filter(
            client=item.client,
            billed_items__description=item.description
        ).distinct().order_by('-date_issued')

    temp_info = {
        'item_id': item.id,
        'item_description': item.description,
        'invoices_found': invoices.count(),
        'invoice_ids': debug_invoice_ids,
        'log_counts_per_invoice': debug_log_counts,
        'log_details_per_invoice': debug_log_details,
        'has_any_logs': any(debug_log_counts),
        'fallback_invoice_ids': [inv.id for inv in fallback_invoices],
    }
    return render(request, "items/item_invoice_email_log.html", {
        'item': item,
        'invoice_logs': invoice_logs,
        'fallback_invoices': fallback_invoices,
        'temp_info': temp_info,
    })
