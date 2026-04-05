import io
import barcode
from barcode.writer import ImageWriter
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponse
from .models import Warehouse, InventoryItem, StockTransaction
from .forms import WarehouseForm, InventoryItemForm, StockTransactionForm



from integrations.models import IntegrationSettings # Make sure this is imported

@login_required
def inventory_item_list(request):
    items = InventoryItem.objects.filter(user=request.user)
    # GET THE SETTINGS FOR THE LOGGED IN USER
    settings, _ = IntegrationSettings.objects.get_or_create(user=request.user)
    
    return render(request, 'inventory/item_list.html', {
        'items': items,
        'barcodes_enabled': settings.barcodes_enabled # Pass the toggle here!
    })

@login_required
def inventory_item_detail(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    settings, _ = IntegrationSettings.objects.get_or_create(user=request.user)
    
    return render(request, 'inventory/item_detail.html', {
        'item': item,
        'barcodes_enabled': settings.barcodes_enabled # And here!
    })


@login_required
def print_barcode(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    
    if not item.barcode:
        messages.error(request, "This item does not have a barcode set.")
        return redirect('inventory:item_detail', pk=item.pk)

    try:
        # Generate barcode using python-barcode
        # We use 'code128' as a standard versatile barcode format
        COD = barcode.get_barcode_class('code128')
        bar = COD(item.barcode, writer=ImageWriter())
        
        # Save to a memory buffer
        buffer = io.BytesIO()
        bar.write(buffer)
        
        return HttpResponse(buffer.getvalue(), content_type="image/png")
    except Exception as e:
        messages.error(request, f"Error generating barcode: {str(e)}")
        return redirect('inventory:item_detail', pk=item.pk)

@login_required
def inventory_item_create(request):
    barcode_param = request.GET.get('barcode')
    settings, _ = IntegrationSettings.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.save()
            messages.success(request, f"Item {item.name} created successfully.")
            return redirect('inventory:item_list')
    else:
        form = InventoryItemForm(initial={'barcode': barcode_param})
    
    return render(request, 'inventory/item_form.html', {
        'form': form, 
        'title': 'Create Inventory Item',
        'barcodes_enabled': settings.barcodes_enabled
    })

@login_required
def inventory_item_update(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    settings, _ = IntegrationSettings.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"Item {item.name} updated successfully.")
            return redirect('inventory:item_list')
    else:
        form = InventoryItemForm(instance=item)
        
    return render(request, 'inventory/item_form.html', {
        'form': form, 
        'title': 'Update Inventory Item',
        'barcodes_enabled': settings.barcodes_enabled
    })

@login_required
def item_by_barcode(request):
    barcode_val = request.GET.get('barcode')
    if not barcode_val:
        messages.error(request, "No barcode provided.")
        return redirect('inventory:item_list')
    
    item = InventoryItem.objects.filter(user=request.user, barcode=barcode_val).first()
    if item:
        return redirect('inventory:item_update', pk=item.pk)
    else:
        messages.info(request, f"No item found with barcode '{barcode_val}'. You can create one now.")
        return redirect(f"{reverse('inventory:item_create')}?barcode={barcode_val}")

@login_required
def warehouse_list(request):
    warehouses = Warehouse.objects.filter(user=request.user)
    return render(request, 'inventory/warehouse_list.html', {'warehouses': warehouses})

@login_required
def warehouse_create(request):
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            warehouse = form.save(commit=False)
            warehouse.user = request.user
            warehouse.save()
            messages.success(request, f"Warehouse {warehouse.name} created successfully.")
            return redirect('inventory:warehouse_list')
    else:
        form = WarehouseForm()
    return render(request, 'inventory/warehouse_form.html', {'form': form, 'title': 'Create Warehouse'})

@login_required
def stock_transaction_create(request):
    if request.method == 'POST':
        form = StockTransactionForm(request.POST, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            
            # Simple stock adjustment logic
            item = transaction.inventory_item
            if transaction.transaction_type == 'IN':
                item.current_stock += transaction.quantity
            elif transaction.transaction_type == 'OUT':
                item.current_stock -= transaction.quantity
            # ADJ logic could be more complex, but let's keep it simple: quantity is the DELTA
            elif transaction.transaction_type == 'ADJ':
                item.current_stock += transaction.quantity
            
            item.save()
            transaction.save()
            messages.success(request, "Stock transaction recorded.")
            return redirect('inventory:item_list')
    else:
        form = StockTransactionForm(user=request.user)
    return render(request, 'inventory/transaction_form.html', {'form': form})
