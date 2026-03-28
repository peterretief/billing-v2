from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Warehouse, InventoryItem, StockTransaction
from .forms import WarehouseForm, InventoryItemForm, StockTransactionForm

@login_required
def inventory_item_list(request):
    items = InventoryItem.objects.filter(user=request.user)
    return render(request, 'inventory/item_list.html', {'items': items})

@login_required
def inventory_item_create(request):
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.user = request.user
            item.save()
            messages.success(request, f"Item {item.name} created successfully.")
            return redirect('inventory:item_list')
    else:
        form = InventoryItemForm()
    return render(request, 'inventory/item_form.html', {'form': form, 'title': 'Create Inventory Item'})

@login_required
def inventory_item_update(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk, user=request.user)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"Item {item.name} updated successfully.")
            return redirect('inventory:item_list')
    else:
        form = InventoryItemForm(instance=item)
    return render(request, 'inventory/item_form.html', {'form': form, 'title': 'Update Inventory Item'})

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
