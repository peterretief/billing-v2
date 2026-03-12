import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView

from invoices.models import Invoice

# ... (your existing imports) ...
from timesheets.forms import TimesheetEntryForm

from .forms import ClientForm
from .models import Client
from .summary import AllClientsSummary, ClientSummary

# views.py


class ClientDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = "clients/client_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object

        # Pulling the related data for the specific client
        context["invoices"] = client.invoices.all().order_by("-date_issued")
        context["unbilled_timesheets"] = client.timesheets.filter(is_billed=False)

        # Pre-fill the form with this client and their default rate
        context["timesheet_form"] = TimesheetEntryForm(
            initial={
                "client": client,
                "hourly_rate": client.default_hourly_rate,  # Using the new field we added
            }
        )
        return context


# --- 1. LIST VIEW (Using our new Manager) ---
class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = "clients/client_list.html"
    context_object_name = "clients"

    paginate_by = 20

    def get_queryset(self):
        qs = Client.objects.filter(user=self.request.user).with_balances()
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(client_code__icontains=q) | Q(email__icontains=q))
        # Ensure consistent ordering for pagination
        return qs.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        return context


# --- 2. EDIT/ADD VIEW (Combined Function) ---
@login_required
def client_edit(request, pk=None):
    if pk:
        client = get_object_or_404(Client, pk=pk, user=request.user)
    else:
        client = Client(user=request.user)

    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client '{client.name}' saved.")
            return redirect("clients:client_list")
    else:
        form = ClientForm(instance=client)

    return render(request, "clients/client_form.html", {"form": form, "is_edit": bool(pk)})


# clients/views.py
from invoices.utils import format_currency

# --- 3. STATEMENT VIEW (Ledger Style) ---


@login_required
def client_statement(request, pk):
    client = get_object_or_404(Client, pk=pk, user=request.user)
    invoices = Invoice.objects.filter(client=client).order_by("-date_issued")

    # Use manager method for totals - simpler and centralized
    stats = {
        "total_billed": format_currency(Invoice.objects.get_client_total_billed(client)),
        "paid": format_currency(Invoice.objects.get_client_total_paid(client)),
        "unpaid": format_currency(Invoice.objects.get_client_outstanding(client)),
    }

    return render(
        request,
        "clients/client_statement.html",
        {
            "client": client,
            "invoices": invoices,
            "stats": stats,
        },
    )


@login_required
def client_statement_csv(request, pk):
    """Export client statement as CSV"""
    client = get_object_or_404(Client, pk=pk, user=request.user)
    invoices = Invoice.objects.filter(client=client).order_by("-date_issued")

    # Create CSV response
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="statement_{client.client_code}_{datetime.now().strftime("%Y%m%d")}.csv"'
    )

    # Create CSV writer
    writer = csv.writer(response)

    # Write header
    writer.writerow(["Client Statement"])
    writer.writerow([f"Client: {client.name}"])
    writer.writerow([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])  # Blank row

    # Write summary stats using manager methods
    raw_stats = {
        "total_billed": Invoice.objects.get_client_total_billed(client),
        "paid": Invoice.objects.get_client_total_paid(client),
        "unpaid": Invoice.objects.get_client_outstanding(client),
    }
    writer.writerow(["SUMMARY"])
    writer.writerow(["Total Billed", f"{raw_stats['total_billed'] or 0:.2f}"])
    writer.writerow(["Total Paid", f"{raw_stats['paid'] or 0:.2f}"])
    writer.writerow(["Current Balance", f"{raw_stats['unpaid'] or 0:.2f}"])
    writer.writerow([])  # Blank row

    # Write invoices
    writer.writerow(["Transaction Details"])
    writer.writerow(["Date", "Invoice #", "Status", "Amount"])
    for inv in invoices:
        writer.writerow([inv.date_issued, inv.number, inv.status, f"{inv.total_amount:.2f}"])

    return response


# --- CLIENT SUMMARY DASHBOARD VIEWS ---


@login_required
def clients_summary_dashboard(request):
    """
    Dashboard showing summary of all clients with quotes, timesheets, items, invoices, and other metrics.
    Allows drill-down to individual client details.
    """
    all_summaries = AllClientsSummary(request.user)
    summaries = all_summaries.get_all_summaries()
    totals = all_summaries.get_totals()

    context = {
        "summaries": summaries,
        "totals": totals,
    }

    return render(request, "clients/clients_summary_dashboard.html", context)


@login_required
def client_summary_detail(request, pk):
    """
    Detailed summary view for a single client.
    Shows breakdown of quotes, timesheets, items, invoices, and other metrics.
    """
    client = get_object_or_404(Client, pk=pk, user=request.user)
    summary = ClientSummary(client).get_summary()

    context = {
        "client": client,
        "summary": summary,
    }

    return render(request, "clients/client_summary_detail.html", context)
