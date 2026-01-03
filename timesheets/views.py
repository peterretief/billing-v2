from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib import messages

# Create your views here.
# timesheets/views.py
from django.shortcuts import render, redirect
from .forms import TimesheetEntryForm


from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import TimesheetEntry

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .models import TimesheetEntry

# ... your other views (TimesheetListView, log_time) ...

def delete_entry(request, pk):
    """
    Placeholder for deleting a timesheet entry.
    """
    # For now, just a safety check and a message
    messages.info(request, "Delete functionality coming soon!")
    return redirect('timesheets:list')


@login_required
def log_time(request):
    if request.method == 'POST':
        form = TimesheetEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user  # Crucial for TenantModel
            entry.save()
            messages.success(request, "Time logged successfully!")
            return redirect('timesheets:list')
    else:
        # If coming from a specific client page, pre-fill the client
        client_id = request.GET.get('client_id')
        form = TimesheetEntryForm(initial={'client': client_id})
        
    return render(request, 'timesheets/log_time.html', {'form': form})


@login_required
def log_time(request):
    if request.method == 'POST':
        form = TimesheetEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, f"Logged {entry.hours} hours for {entry.client.name}")
            # Redirect back to the client detail page
            return redirect(request.META.get('HTTP_REFERER', 'clients:client_list'))
    return redirect('clients:client_list')
    
class TimesheetListView(LoginRequiredMixin, ListView):
    model = TimesheetEntry
    template_name = 'timesheets/timesheet_list.html'
    context_object_name = 'entries'

    def get_queryset(self):
        # Change self.user to self.request.user
        #return TimesheetEntry.objects.filter(user=self.request.user).order_back('-date')
        return TimesheetEntry.objects.filter(user=self.request.user).order_by('-date')