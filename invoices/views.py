from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.template.loader import render_to_string

from .models import Invoice
from .forms import InvoiceForm, InvoiceItemFormSet
from .utils import generate_invoice_pdf
from django.db.models import Sum
from decimal import Decimal

@login_required
def dashboard(request):
    """A main overview of recent invoices."""
    invoices = Invoice.objects.filter(user=request.user).order_by('-date_issued')[:5]
    return render(request, 'invoices/dashboard.html', {'invoices': invoices})


from django.core.paginator import Paginator

@login_required
def invoice_list(request):
    # 1. Get the stats from your new manager
    stats = Invoice.objects.get_dashboard_stats(request.user)
    
    # 2. Get the full list of invoices
    invoice_list = Invoice.objects.filter(user=request.user).order_by('-date_issued')
    
    # 3. Set up Pagination (e.g., 10 invoices per page)
    paginator = Paginator(invoice_list, 10) 
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'invoices/invoice_list.html', {
        'invoices': page_obj,  # This replaces the full list with the paged list
        'stats': stats
    })


# --- INVOICE CRUD VIEWS ---

@login_required
def invoice_create(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.user = request.user
            invoice.save()
            
            # This links the items to the invoice automatically
            formset.instance = invoice
            formset.save()
            return redirect('invoices:list')
    else:
        form = InvoiceForm()
        formset = InvoiceItemFormSet()

    return render(request, 'invoices/invoice_form.html', {
        'form': form,
        'formset': formset
    })


"""
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
            invoice.save()
            formset.instance = invoice
            formset.save()
            messages.success(request, "Invoice created.")
            return redirect('clients:detail', pk=invoice.client.id)
    else:
        form = InvoiceForm(initial=initial_data)
        formset = InvoiceItemFormSet()
    
    return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset})
"""
    

@login_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Invoice updated.")
            return redirect('clients:detail', pk=invoice.client.id)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice)
    
    return render(request, 'invoices/invoice_form.html', {'form': form, 'formset': formset, 'invoice': invoice})

@login_required
def invoice_detail(request, pk):
    """View a single invoice's details in the browser."""
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    return render(request, 'invoices/invoice_detail.html', {'invoice': invoice})

# --- PDF GENERATION ---

@login_required
def generate_invoice_pdf_view(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk, user=request.user)
    try:
        pdf_content = generate_invoice_pdf(invoice)
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="Invoice_{invoice.number}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f"PDF Error: {str(e)}")
        return redirect('invoices:list')

# --- HTMX HELPERS ---

@login_required
def add_item_row(request):
    """Used for dynamic formsets to add a new item line."""
    formset = InvoiceItemFormSet()
    # We take just one empty form from the formset to send back to the page
    form = formset.forms[0]
    return render(request, 'invoices/partials/item_row.html', {'item_form': form})

# --- PROFILE VIEWS ---
