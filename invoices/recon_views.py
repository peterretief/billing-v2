"""
Views for reconciliation statements - client recon and all-clients summary.
"""
from datetime import date
from decimal import Decimal
import csv
import io

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, FileResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import Coalesce

from clients.models import Client
from invoices.models import Invoice, CreditNote
from invoices.reconciliation import ClientReconciliation, AllClientsReconciliation

# For PDF generation
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


@login_required
@require_http_methods(["GET"])
def client_reconciliation_statement(request, client_id):
    """
    Generate reconciliation statement for a specific client.
    Shows summary and detailed transaction list.
    """
    client = get_object_or_404(Client, id=client_id, user=request.user)
    
    # Get optional date range from query params
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date', date.today().isoformat())
    
    start_date = None
    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            start_date = None
    
    try:
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        end_date = date.today()
    
    # Generate reconciliation
    recon = ClientReconciliation(client, request.user, start_date, end_date)
    report_data = recon.get_full_report()
    
    context = {
        'client': client,
        'report': report_data,
        'currency': request.user.profile.currency,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'invoices/client_reconciliation.html', context)


@login_required
@require_http_methods(["GET"])
def all_clients_reconciliation(request):
    """
    Generate summary reconciliation for all clients.
    Shows outstanding balance, payments, credits for each client.
    """
    end_date = request.GET.get('end_date', date.today().isoformat())
    
    try:
        end_date = date.fromisoformat(end_date)
    except ValueError:
        end_date = date.today()
    
    recon = AllClientsReconciliation(request.user, end_date)
    summaries = recon.get_all_clients_summary()
    
    # Calculate totals
    total_outstanding = sum(s['outstanding_balance'] for s in summaries)
    total_payments = sum(s['total_payments'] for s in summaries)
    total_credits = sum(s['credit_balance'] for s in summaries)
    
    context = {
        'summaries': summaries,
        'end_date': end_date,
        'currency': request.user.profile.currency,
        'totals': {
            'outstanding': total_outstanding,
            'payments': total_payments,
            'credits': total_credits,
            'client_count': len(summaries),
        }
    }
    
    return render(request, 'invoices/all_clients_reconciliation.html', context)


@login_required
@require_http_methods(["GET"])
def client_reconciliation_pdf(request, client_id):
    """Export client reconciliation as PDF."""
    if not REPORTLAB_AVAILABLE:
        return HttpResponse("PDF generation not available. Install reportlab.", status=400)
    
    client = get_object_or_404(Client, id=client_id, user=request.user)
    
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date', date.today().isoformat())
    
    start_date = None
    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            start_date = None
    
    try:
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        end_date = date.today()
    
    recon = ClientReconciliation(client, request.user, start_date, end_date)
    report_data = recon.get_full_report()
    
    # Create PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=12,
    )
    
    elements = []
    
    # Title
    elements.append(Paragraph(f"Reconciliation Statement - {client.name}", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Summary table
    summary = report_data['summary']
    summary_data = [
        ['Period', f"{report_data['period_start']} to {report_data['period_end']}"],
        ['Opening Balance', f"{request.user.profile.currency} {summary['opening_balance']:.2f}"],
        ['Invoices Sent', f"{request.user.profile.currency} {summary['invoices_sent']:.2f}"],
        ['Invoices Cancelled', f"{request.user.profile.currency} {summary['invoices_cancelled']:.2f}"],
        ['Payments Received', f"{request.user.profile.currency} {summary['payments_received']:.2f}"],
        ['Credit Notes Issued', f"{request.user.profile.currency} {summary['credit_notes_issued']:.2f}"],
        ['Closing Balance', f"{request.user.profile.currency} {summary['closing_balance']:.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[2*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (1, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Transactions table
    elements.append(Paragraph("Transaction Details", title_style))
    elements.append(Spacer(1, 0.1*inch))
    
    trans_data = [['Date', 'Description', 'Amount', 'Balance']]
    for trans in report_data['transactions']:
        trans_data.append([
            str(trans['date']),
            trans['description'][:40],  # Truncate for PDF
            f"{trans['amount']:.2f}",
            f"{trans['running_balance']:.2f}",
        ])
    
    if len(trans_data) > 1:
        trans_table = Table(trans_data, colWidths=[1*inch, 2.5*inch, 1*inch, 1*inch])
        trans_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ]))
        elements.append(trans_table)
    
    doc.build(elements)
    buffer.seek(0)
    
    response = FileResponse(buffer, as_attachment=True, filename=f'reconciliation_{client.id}_{date.today()}.pdf')
    response['Content-Type'] = 'application/pdf'
    return response


@login_required
@require_http_methods(["GET"])
def all_clients_reconciliation_csv(request):
    """Export all clients reconciliation as CSV."""
    end_date = request.GET.get('end_date', date.today().isoformat())
    
    try:
        end_date = date.fromisoformat(end_date)
    except ValueError:
        end_date = date.today()
    
    recon = AllClientsReconciliation(request.user, end_date)
    summaries = recon.get_all_clients_summary()
    
    # Create CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="reconciliation_{date.today()}.csv"'
    
    writer = csv.writer(response)
    
    # Header
    writer.writerow([
        'Client',
        'Outstanding Balance',
        'Total Payments',
        'Credit Balance',
        'Cancelled Sent',
        'Total Invoices',
        'Net Position'
    ])
    
    # Data rows
    for summary in summaries:
        writer.writerow([
            summary['client'].name,
            f"{summary['outstanding_balance']:.2f}",
            f"{summary['total_payments']:.2f}",
            f"{summary['credit_balance']:.2f}",
            summary['cancelled_sent_count'],
            summary['total_invoices'],
            f"{summary['net_position']:.2f}",
        ])
    
    # Totals row
    total_outstanding = sum(s['outstanding_balance'] for s in summaries)
    total_payments = sum(s['total_payments'] for s in summaries)
    total_credits = sum(s['credit_balance'] for s in summaries)
    
    writer.writerow([])
    writer.writerow(['TOTALS', f"{total_outstanding:.2f}", f"{total_payments:.2f}", f"{total_credits:.2f}"])
    
    return response


@login_required
@require_http_methods(["GET"])
def client_reconciliation_csv(request, client_id):
    """Export client reconciliation as CSV."""
    client = get_object_or_404(Client, id=client_id, user=request.user)
    
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date', date.today().isoformat())
    
    start_date = None
    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
        except ValueError:
            start_date = None
    
    try:
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        end_date = date.today()
    
    recon = ClientReconciliation(client, request.user, start_date, end_date)
    report_data = recon.get_full_report()
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="reconciliation_{client.id}_{date.today()}.csv"'
    
    writer = csv.writer(response)
    
    # Header info
    writer.writerow(['Client Reconciliation Statement'])
    writer.writerow(['Client', client.name])
    writer.writerow(['Period', f"{report_data['period_start']} to {report_data['period_end']}"])
    writer.writerow([])
    
    # Summary
    summary = report_data['summary']
    writer.writerow(['SUMMARY'])
    writer.writerow(['Opening Balance', f"{summary['opening_balance']:.2f}"])
    writer.writerow(['Invoices Sent', f"{summary['invoices_sent']:.2f}"])
    writer.writerow(['Invoices Cancelled', f"{summary['invoices_cancelled']:.2f}"])
    writer.writerow(['Payments Received', f"{summary['payments_received']:.2f}"])
    writer.writerow(['Credit Notes', f"{summary['credit_notes_issued']:.2f}"])
    writer.writerow(['Closing Balance', f"{summary['closing_balance']:.2f}"])
    writer.writerow([])
    
    # Transactions
    writer.writerow(['TRANSACTIONS'])
    writer.writerow(['Date', 'Type', 'Description', 'Amount', 'Running Balance'])
    
    for trans in report_data['transactions']:
        writer.writerow([
            trans['date'],
            trans['type'],
            trans['description'],
            f"{trans['amount']:.2f}",
            f"{trans['running_balance']:.2f}",
        ])
    
    return response
