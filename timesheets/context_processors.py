from .models import TimesheetEntry

def unbilled_count(request):
    if request.user.is_authenticated:
        count = TimesheetEntry.objects.filter(user=request.user, is_billed=False).count()
        return {'unbilled_count': count}
    return {'unbilled_count': 0}