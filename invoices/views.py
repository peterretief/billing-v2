from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.core.paginator import Paginator

from .models import Invoice
from .forms import InvoiceForm, InvoiceItemFormSet
from .utils import generate_invoice_pdf

@login_required
def dashboard(request):
    # Stats pulled from the custom Manager
    stats = Invoice.objects.get_dashboard_stats(request.user)
    invoices = Invoice.objects.filter(user=request.user).order_by('-date_issued', '-id')[:10]
    return render(request, 'invoices/dashboard.html', {
        'stats': stats, 
        'invoices': invoices
    })

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