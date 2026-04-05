from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import IntegrationSettings
from .forms import IntegrationSettingsForm

@login_required
def settings_view(request):
    settings, created = IntegrationSettings.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = IntegrationSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Integration settings updated successfully.")
            return redirect('integrations:settings')
    else:
        form = IntegrationSettingsForm(instance=settings)
    
    return render(request, 'integrations/settings.html', {
        'form': form,
        'settings': settings
    })
