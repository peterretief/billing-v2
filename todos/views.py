from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy

from timesheets.models import WorkCategory
from timesheets.forms import TimesheetEntryForm

from .models import Todo
from .forms import TodoForm


class TodoListView(LoginRequiredMixin, ListView):
    """Display all todos for the current user."""
    model = Todo
    template_name = 'todos/todo_list.html'
    context_object_name = 'todos'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Todo.objects.filter(user=self.request.user).select_related('client')
        
        # Filter by status if provided
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by priority if provided
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by client if provided
        client_id = self.request.GET.get('client')
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        
        # Search by title or description
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add filter options
        context['statuses'] = Todo.Status.choices
        context['priorities'] = Todo.Priority.choices
        context['clients'] = self.request.user.client_related.all()
        
        # Add current filters for template
        context['current_status'] = self.request.GET.get('status', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['current_client'] = self.request.GET.get('client', '')
        context['search_query'] = self.request.GET.get('search', '')
        
        return context


class TodoCreateView(LoginRequiredMixin, CreateView):
    """Create a new todo."""
    model = Todo
    form_class = TodoForm
    template_name = 'todos/todo_form.html'
    success_url = reverse_lazy('todos:todo_list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Todo '{form.instance.title}' created successfully!")
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class TodoDetailView(LoginRequiredMixin, DetailView):
    """Display todo details."""
    model = Todo
    template_name = 'todos/todo_detail.html'
    context_object_name = 'todo'
    
    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get linked timesheets
        context['linked_timesheets'] = self.object.timesheet_entries.select_related('client', 'category')
        
        # Add timesheet form and categories for the log time modal
        context['timesheet_form'] = TimesheetEntryForm()
        context['categories'] = WorkCategory.objects.filter(user=self.request.user)
        context['clients'] = self.request.user.client_related.all()
        
        return context


class TodoUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing todo."""
    model = Todo
    form_class = TodoForm
    template_name = 'todos/todo_form.html'
    
    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('todos:todo_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, f"Todo '{form.instance.title}' updated!")
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class TodoDeleteView(LoginRequiredMixin, DeleteView):
    """Delete a todo."""
    model = Todo
    template_name = 'todos/todo_confirm_delete.html'
    success_url = reverse_lazy('todos:todo_list')
    
    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        todo = self.get_object()
        messages.success(request, f"Todo '{todo.title}' deleted!")
        return super().delete(request, *args, **kwargs)


@login_required
def mark_todo_completed(request, pk):
    """Mark a todo as completed."""
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.mark_completed()
    messages.success(request, f"Todo '{todo.title}' marked as completed!")
    return redirect('todos:todo_detail', pk=pk)


@login_required
def mark_todo_cancelled(request, pk):
    """Mark a todo as cancelled."""
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    todo.mark_cancelled()
    messages.success(request, f"Todo '{todo.title}' cancelled!")
    return redirect('todos:todo_detail', pk=pk)
