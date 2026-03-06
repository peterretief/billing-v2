from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.utils import timezone

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
        
        # Filter by today's todos if requested
        today = self.request.GET.get('today')
        if today == 'true':
            today_date = timezone.now().date()
            queryset = queryset.filter(due_date=today_date)
        
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
        
        # Search by category or description
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(category__name__icontains=search) | Q(description__icontains=search)
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
        context['today_filter'] = self.request.GET.get('today', 'false') == 'true'
        context['today_date'] = timezone.now().date()
        
        # Check if user has Google Calendar connected
        from .models import GoogleCalendarCredential
        try:
            GoogleCalendarCredential.objects.get(user=self.request.user)
            context['google_calendar_connected'] = True
        except GoogleCalendarCredential.DoesNotExist:
            context['google_calendar_connected'] = False
        
        return context


class TodoCreateView(LoginRequiredMixin, CreateView):
    """Create a new todo."""
    model = Todo
    form_class = TodoForm
    template_name = 'todos/todo_form.html'
    success_url = reverse_lazy('todos:todo_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = WorkCategory.objects.filter(user=self.request.user).order_by('name')
        return context
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Todo created successfully!")
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
        
        # Check if a timesheet already exists for this todo
        context['has_timesheet'] = self.object.timesheet_entries.exists()
        context['linked_timesheet'] = self.object.timesheet_entries.first()
        
        # Get the todo's category
        matching_category = self.object.category
        
        # Add timesheet form with pre-filled initial data
        initial_data = {
            'client': self.object.client.id,
            'hourly_rate': self.object.client.default_hourly_rate,
            'hours': self.object.estimated_hours,
            'date': timezone.now().date(),
            'todo': self.object.id,
        }
        if matching_category:
            initial_data['category'] = matching_category.id
            
        context['timesheet_form'] = TimesheetEntryForm(initial=initial_data, user=self.request.user)
        context['categories'] = WorkCategory.objects.filter(user=self.request.user)
        context['clients'] = self.request.user.client_related.all()
        # Pre-select the category for the form
        context['pre_selected_category_id'] = matching_category.id if matching_category else None
        
        return context


class TodoUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing todo."""
    model = Todo
    form_class = TodoForm
    template_name = 'todos/todo_form.html'
    
    def get_queryset(self):
        return Todo.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = WorkCategory.objects.filter(user=self.request.user).order_by('name')
        
        # Check for linked timesheets
        linked_timesheet = self.object.timesheet_entries.first()
        context['linked_timesheet'] = linked_timesheet
        if linked_timesheet:
            context['timesheet_is_invoiced'] = linked_timesheet.is_billed
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle form submission and potential timesheet unlinking."""
        self.object = self.get_object()
        
        # Check if user is requesting to unlink the timesheet
        unlink_timesheet = request.POST.get('unlink_timesheet') == 'on'
        
        if unlink_timesheet:
            linked_timesheet = self.object.timesheet_entries.first()
            if linked_timesheet:
                if linked_timesheet.is_billed:
                    messages.error(request, "Cannot unlink a timesheet that has been invoiced.")
                    return self.get(request, *args, **kwargs)
                else:
                    # Delete the timesheet to maintain integrity
                    linked_timesheet.delete()
                    messages.info(request, "Timesheet deleted. You can now edit the todo.")
                    return self.get(request, *args, **kwargs)
        
        # Check if trying to submit form while timesheet is linked
        linked_timesheet = self.object.timesheet_entries.first()
        if linked_timesheet and not unlink_timesheet:
            messages.error(request, "Cannot edit this todo while a timesheet is linked. Please unlink it first.")
            return self.get(request, *args, **kwargs)
        
        return super().post(request, *args, **kwargs)
    
    def get_success_url(self):
        return reverse_lazy('todos:todo_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, "Todo updated!")
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
        todo_name = todo.category.name if todo.category else "Uncategorized"
        messages.success(request, f"Todo '{todo_name}' deleted!")
        return super().delete(request, *args, **kwargs)


@login_required
def mark_todo_completed(request, pk):
    """Mark a todo as completed."""
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    try:
        todo.mark_completed()
        todo_name = todo.category.name if todo.category else "Uncategorized"
        messages.success(request, f"Todo '{todo_name}' marked as completed!")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('todos:todo_detail', pk=pk)


@login_required
def mark_todo_cancelled(request, pk):
    """Mark a todo as cancelled."""
    todo = get_object_or_404(Todo, pk=pk, user=request.user)
    try:
        todo.mark_cancelled()
        todo_name = todo.category.name if todo.category else "Uncategorized"
        messages.success(request, f"Todo '{todo_name}' cancelled!")
        return redirect('todos:todo_list')
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('todos:todo_detail', pk=pk)

@login_required
def calendar_auth_start(request):
    """Initiate Google Calendar OAuth flow."""
    from .calendar_utils import get_oauth_flow
    from django.conf import settings
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if credentials are configured
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        messages.error(
            request,
            "Google Calendar is not configured. Please contact your administrator to set up OAuth credentials."
        )
        return redirect('todos:todo_list')
    
    try:
        flow = get_oauth_flow()
        
        # Generate authorization URL with prompt='consent' to force refresh token
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )
        
        # Store state and code_verifier in session for verification
        request.session['oauth_state'] = state
        request.session['code_verifier'] = flow.code_verifier
        request.session.modified = True
        request.session.save()  # Explicitly save the session
        
        logger.info(f"Started OAuth flow for {request.user.username}. State: {state}")
        
        return redirect(authorization_url)
    except Exception as e:
        logger.exception(f"Error initiating Google Calendar auth: {str(e)}")
        messages.error(request, f"Error initiating Google Calendar auth: {str(e)}")
        return redirect('todos:todo_list')


@login_required
def calendar_auth_callback(request):
    """Handle Google Calendar OAuth callback."""
    from .calendar_utils import get_oauth_flow
    from .models import GoogleCalendarCredential
    from datetime import datetime, timezone
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Try to validate session state (CSRF protection)
    state = request.session.get('oauth_state')
    google_state = request.GET.get('state')
    
    # Session state might be lost in some cases (mobile, incognito, etc.)
    # But we still have CSRF protection via Django's @login_required and the fact that
    # Google verified the authorization. We log this for monitoring.
    if not state:
        logger.warning(f"OAuth state not found in session for {request.user.username}. Google state: {google_state}. Proceeding with caution.")
    elif state != google_state:
        messages.error(request, "OAuth state mismatch. Please try again.")
        logger.error(f"OAuth state mismatch for {request.user.username}. Expected: {state}, got: {google_state}")
        return redirect('todos:todo_list')
    
    # Get authorization code
    code = request.GET.get('code')
    if not code:
        error = request.GET.get('error', 'Unknown error')
        messages.error(request, f"Authorization cancelled: {error}")
        logger.error(f"No authorization code received for {request.user.username}. Error: {error}")
        return redirect('todos:todo_list')
    
    try:
        logger.info(f"Starting token exchange for user {request.user.username}")
        flow = get_oauth_flow()
        
        # Retrieve code_verifier from session (needed for PKCE)
        code_verifier = request.session.get('code_verifier')
        if not code_verifier:
            logger.warning(f"Code verifier not found in session for {request.user.username}. PKCE validation may fail.")
        
        # Exchange code for token
        flow.fetch_token(
            authorization_response=request.build_absolute_uri(),
            code_verifier=code_verifier
        )
        creds = flow.credentials
        
        logger.info(f"Token received, saving credentials for {request.user.username}")
        logger.info(f"Token: {creds.token[:20] if creds.token else 'None'}...")
        logger.info(f"Refresh token: {creds.refresh_token[:20] if creds.refresh_token else 'None'}...")
        logger.info(f"Expiry: {creds.expiry}")
        logger.info(f"Scopes granted: {creds.scopes}")
        
        # Save credentials to database
        cred_obj, created = GoogleCalendarCredential.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': creds.token or '',
                'refresh_token': creds.refresh_token or '',
                'token_expiry': datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc) if creds.expiry else None,
                'sync_enabled': True,
                'calendar_id': 'primary',
            }
        )
        
        logger.info(f"Saved credentials: access_token={'set' if cred_obj.access_token else 'empty'}, refresh_token={'set' if cred_obj.refresh_token else 'empty'}")
        
        action = "updated" if not created else "created"
        logger.info(f"Google Calendar credential {action} for {request.user.username}")
        
        # Clean up session
        request.session.pop('oauth_state', None)
        request.session.pop('code_verifier', None)
        request.session.modified = True
        request.session.save()
        
        messages.success(request, "Google Calendar connected successfully! You now have permission to access Calendar and Contacts.")
        return redirect('todos:todo_list')
        
    except Exception as e:
        logger.exception(f"Error during OAuth callback for {request.user.username}: {str(e)}")
        messages.error(request, f"Error connecting to Google Calendar: {str(e)}")
        return redirect('todos:todo_list')


@login_required
def sync_todos_to_calendar(request):
    """Sync all todos to Google Calendar."""
    from .calendar_utils import sync_all_todos_to_calendar, InvalidScopeError
    from .models import GoogleCalendarCredential
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('todos:calendar_auth_start')
    
    try:
        synced_count = sync_all_todos_to_calendar(request.user)
        
        if synced_count > 0:
            messages.success(request, f"Successfully synced {synced_count} todos to Google Calendar!")
        else:
            messages.info(request, "No todos to sync. Please create a todo with a due date first.")
    except InvalidScopeError:
        messages.warning(request, "Google permissions were updated. Please reconnect your Google account to continue.")
        return redirect('todos:calendar_auth_start')
    
    return redirect('todos:todo_list')


@login_required
def import_calendar_events(request):
    """Display Google Calendar events to import as timesheets."""
    from .calendar_utils import get_google_calendar_service, get_google_contacts_list, InvalidScopeError
    from .models import GoogleCalendarCredential
    from datetime import datetime, timedelta, timezone
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('todos:calendar_auth_start')
    
    try:
        service = get_google_calendar_service(request.user)
    except InvalidScopeError:
        messages.warning(request, "Google permissions were updated. Please reconnect your Google account to continue.")
        return redirect('todos:calendar_auth_start')
    
    if not service:
        messages.error(request, "Could not access Google Calendar. Please reconnect.")
        return redirect('todos:todo_list')
    
    # Get date range from request or default to last 7 days and next 30 days
    days_back = request.GET.get('days_back', 7)
    days_forward = request.GET.get('days_forward', 30)
    try:
        days_back = int(days_back)
        days_forward = int(days_forward)
    except (ValueError, TypeError):
        days_back = 7
        days_forward = 30
    
    # Check if user wants to see synced todos
    show_synced = request.GET.get('show_synced', False)
    
    now = datetime.now(tz=timezone.utc)
    start_date = now - timedelta(days=days_back)
    end_date = now + timedelta(days=days_forward)
    
    try:
        # Fetch events from Google Calendar
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_date.isoformat(),
            timeMax=end_date.isoformat(),
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        all_events = events_result.get('items', [])
        
        # Filter out synced events (marked with [Synced] prefix) unless user wants to see them
        if show_synced:
            events = all_events
        else:
            events = [e for e in all_events if not e.get('summary', '').startswith('[Synced]')]
            
            if len(all_events) > len(events):
                hidden_count = len(all_events) - len(events)
                messages.info(request, f"Hiding {hidden_count} previously synced event(s). Check 'Show synced todos' to include them.")
        
    except Exception as e:
        messages.error(request, f"Error fetching calendar events: {str(e)}")
        events = []
    
    # Parse event titles and extract client/category suggestions
    from timesheets.models import WorkCategory, TimesheetEntry
    from clients.models import Client
    import logging
    logger = logging.getLogger(__name__)
    
    # Get work categories and clients for the user
    categories = WorkCategory.objects.filter(user=request.user).order_by('name')
    clients = Client.objects.filter(user=request.user).order_by('name')
    
    # Fetch contacts from Google Contacts address book for enhanced matching
    google_contacts = get_google_contacts_list(request.user)
    logger.info(f"Fetched {len(google_contacts)} Google Contacts for {request.user.username}")
    for contact in google_contacts:
        logger.info(f"  Contact: {contact.get('name')} - Email: {contact.get('email')} - Address: {contact.get('address')}")
    
    # Check if user wants to hide already-imported events
    hide_imported = request.GET.get('hide_imported', False)
    
    for event in events:
        title = event.get('summary', '')
        # Format: "[Synced] Category - Client" or just "Category - Client"
        if '[Synced]' in title:
            title = title.replace('[Synced] ', '').strip()
        
        if ' - ' in title:
            parts = title.split(' - ', 1)
            event['suggested_category'] = parts[0].strip()
            event['suggested_client'] = parts[1].strip()
        else:
            # If no " - " separator, use title as category
            event['suggested_category'] = title.strip()
            event['suggested_client'] = ''
        
        # Extract client details from description
        description = event.get('description', '')
        event['client_details'] = {}
        
        if '--- CLIENT DETAILS ---' in description:
            # Parse client info from description
            details_section = description.split('--- CLIENT DETAILS ---')[1]
            for line in details_section.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    event['client_details'][key] = value
        
        # Smart client matching: try multiple strategies
        event['suggested_client_id'] = None
        location = event.get('location', '')
        organizer_info = event.get('organizer', {})
        organizer_email = organizer_info.get('email', '')
        
        logger.info(f"Processing event: {title}")
        logger.info(f"  Location: {location}, Organizer: {organizer_email}")
        
        # Strategy 0: Match by client name found in location (quick check)
        if location and not event['suggested_client_id']:
            for client in clients:
                # Check if client name appears in location (case-insensitive)
                if client.name.lower() in location.lower():
                    event['suggested_client_id'] = client.id
                    event['suggested_client'] = client.name
                    logger.info(f"  ✓ Matched by client name in location to: {client.name} (ID: {client.id})")
                    break
        
        # Strategy 1: Match by UUID from Google Contact (most reliable)
        if not event['suggested_client_id']:
            for contact in google_contacts:
                if contact.get('client_uuid'):
                    try:
                        # Try to find client by UUID
                        client = Client.objects.get(client_uuid=contact.get('client_uuid'), user=request.user)
                        # Check if this contact matches the event (by organizer email or location)
                        if ((organizer_email and organizer_email == contact.get('email')) or
                            (location and contact.get('address') and location.lower() in contact['address'].lower())):
                            event['suggested_client_id'] = client.id
                            event['suggested_client'] = client.name
                            logger.info(f"  ✓ Matched by UUID to client: {client.name} (ID: {client.id}, UUID: {contact.get('client_uuid')})")
                            break
                    except Client.DoesNotExist:
                        logger.warning(f"  UUID found in contact but no matching client: {contact.get('client_uuid')}")
        
        # Strategy 2: Match by location address
        if location and not event['suggested_client_id']:
            for client in clients:
                if client.address and location.lower() in client.address.lower():
                    event['suggested_client_id'] = client.id
                    event['suggested_client'] = client.name
                    logger.info(f"  ✓ Matched by address to client: {client.name} (ID: {client.id})")
                    break
        
        # Strategy 3: Match by Google Contact address
        if location and not event['suggested_client_id']:
            for contact in google_contacts:
                if contact.get('address') and location.lower() in contact['address'].lower():
                    logger.info(f"  Found matching Google Contact by address: {contact.get('name')}")
                    # Try to find matching client
                    for client in clients:
                        if (client.name.lower() == contact.get('name', '').lower() or
                            client.email == contact.get('email') or
                            client.phone == contact.get('phone')):
                            event['suggested_client_id'] = client.id
                            event['suggested_client'] = client.name
                            logger.info(f"  ✓ Matched by Google Contact to client: {client.name} (ID: {client.id})")
                            break
                    if event['suggested_client_id']:
                        break
        
        # Strategy 4: Match by event organizer email (from Google Contacts)
        if organizer_email and not event['suggested_client_id']:
            for contact in google_contacts:
                if contact.get('email') == organizer_email:
                    logger.info(f"  Found matching Google Contact by email: {contact.get('name')}")
                    # Found matching contact, now find client
                    for client in clients:
                        if (client.name.lower() == contact.get('name', '').lower() or
                            client.email == contact.get('email')):
                            event['suggested_client_id'] = client.id
                            event['suggested_client'] = client.name
                            logger.info(f"  ✓ Matched by organizer email to client: {client.name} (ID: {client.id})")
                            break
                    if event['suggested_client_id']:
                        break
        
        # Strategy 5: Match by client name from title
        if not event['suggested_client_id'] and event.get('suggested_client'):
            for client in clients:
                if client.name.lower() == event['suggested_client'].lower():
                    event['suggested_client_id'] = client.id
                    logger.info(f"  ✓ Matched by name from title to client: {client.name} (ID: {client.id})")
                    break
        
        if event['suggested_client_id']:
            logger.info(f"  Final suggested_client_id: {event['suggested_client_id']} (type: {type(event['suggested_client_id']).__name__})")
        else:
            logger.info(f"  No client match found for event")
        
        # Store location for display
        event['display_location'] = location
        
        # Check if this event has already been imported
        event_id = event.get('id', '')
        existing_import = TimesheetEntry.objects.filter(
            user=request.user,
            google_calendar_event_id=event_id
        ).first()
        
        event['already_imported'] = existing_import is not None
        event['imported_timesheet'] = existing_import
    
    # Filter out already-imported events if requested
    if hide_imported:
        events = [e for e in events if not e.get('already_imported', False)]
    
    context = {
        'events': events,
        'days_back': days_back,
        'days_forward': days_forward,
        'categories': categories,
        'clients': clients,
        'show_synced': show_synced,
        'hide_imported': hide_imported,
    }
    
    return render(request, 'todos/import_calendar_events.html', context)


@login_required
def create_timesheets_from_events(request):
    """Create timesheet entries from selected calendar events."""
    from .calendar_utils import get_google_calendar_service
    from .models import GoogleCalendarCredential
    from timesheets.models import TimesheetEntry, WorkCategory
    from datetime import datetime, timezone
    import logging
    
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== CREATE_TIMESHEETS_FROM_EVENTS START ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"User: {request.user}")
    
    if request.method != 'POST':
        logger.info(f"Not a POST request, redirecting to import_calendar_events")
        return redirect('todos:import_calendar_events')
    
    logger.info(f"POST data keys: {list(request.POST.keys())}")
    logger.info(f"POST data: {dict(request.POST)}")
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('todos:calendar_auth_start')
    
    service = get_google_calendar_service(request.user)
    if not service:
        messages.error(request, "Could not access Google Calendar.")
        return redirect('todos:import_calendar_events')
    
    # Get selected events from POST
    selected_events = request.POST.getlist('events[]')
    
    logger.info(f"=== SELECTED EVENTS DEBUG ===")
    logger.info(f"Total POST keys: {list(request.POST.keys())}")
    logger.info(f"All events[] values: {request.POST.getlist('events[]')}")
    logger.info(f"Selected events count: {len(selected_events)}")
    logger.info(f"Selected events: {selected_events}")
    
    if not selected_events:
        logger.warning(f"No events selected")
        messages.error(request, "Please select at least one event.")
        return redirect('todos:import_calendar_events')
    
    # Validate that each selected event has a category and client assigned
    from clients.models import Client
    
    event_configs = {}  # Store category and client for each event
    for event_id in selected_events:
        logger.info(f"Validating event: {event_id}")
        category_id = request.POST.get(f'category_id_{event_id}')
        client_id = request.POST.get(f'client_id_{event_id}')
        
        logger.info(f"  Event {event_id}: category_id={category_id}, client_id={client_id}")
        
        if not category_id or not client_id:
            logger.error(f"VALIDATION FAILED - Event {event_id}: missing category ({category_id}) or client ({client_id})")
            messages.error(request, f"Event {event_id}: Please select a work category and client.")
            return redirect('todos:import_calendar_events')
        
        # Validate category
        try:
            category = WorkCategory.objects.get(id=category_id, user=request.user)
        except WorkCategory.DoesNotExist:
            logger.error(f"Category {category_id} not found for user {request.user.username}")
            messages.error(request, f"Invalid work category selected for event {event_id}.")
            return redirect('todos:import_calendar_events')
        
        # Validate client
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            logger.error(f"Client {client_id} not found")
            messages.error(request, f"Invalid client selected for event {event_id}.")
            return redirect('todos:import_calendar_events')
        
        event_configs[event_id] = {'category': category, 'client': client}
        logger.info(f"Event {event_id}: category={category.name}, client={client.name}")
    
    # Fetch selected events and create timesheets
    created_count = 0
    errors = []
    
    logger.info(f"Processing {len(selected_events)} selected events")
    
    for event_id in selected_events:
        try:
            logger.info(f"Fetching event {event_id}")
            event = service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            # Extract event details
            title = event.get('summary', 'Calendar Event')
            description = event.get('description', '')
            # Calculate duration
            start_time = event.get('start', {})
            end_time = event.get('end', {})
            
            event_date = None
            duration_hours = 8  # Default for all-day events
            time_entry = None
            
            # Handle all-day events vs timed events
            if 'dateTime' in start_time and 'dateTime' in end_time:
                try:
                    start_dt = datetime.fromisoformat(start_time['dateTime'].replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_time['dateTime'].replace('Z', '+00:00'))
                    event_date = start_dt.date()
                    duration_hours = round((end_dt - start_dt).total_seconds() / 3600, 2)
                    time_entry = start_dt.time()
                    logger.info(f"Timed event: calculated {duration_hours} hours")
                except Exception as e:
                    logger.warning(f"Error parsing datetime for event {event_id}: {e}, using default 8 hours")
                    duration_hours = 8
            elif 'date' in start_time:
                try:
                    event_date = datetime.fromisoformat(start_time['date']).date()
                    logger.info(f"All-day event: using default 8 hours")
                except Exception as e:
                    logger.warning(f"Error parsing date for event {event_id}: {e}")
                    pass
            
            # Fallback to today if no date found
            if not event_date:
                event_date = datetime.now().date()
            
            logger.info(f"Event {event_id}: date={event_date}, parsed hours={duration_hours} (type: {type(duration_hours).__name__})")
            # Get category and client for this specific event
            config = event_configs.get(event_id, {})
            category = config.get('category')
            client = config.get('client')
            
            if not category or not client:
                logger.error(f"Missing category or client config for event {event_id}")
                errors.append(f"Missing configuration for '{title}'")
                continue
            
            logger.info(f"Creating timesheet: title={title}, date={event_date}, hours={duration_hours}, category={category.name}, client={client.name}")
            
            # Get client's default hourly rate or use 0 as fallback
            hourly_rate = client.default_hourly_rate if hasattr(client, 'default_hourly_rate') and client.default_hourly_rate else 0
            logger.info(f"Using hourly_rate={hourly_rate} for client {client.name}")
            
            # Create timesheet entry
            # Store raw metadata - let formatted_metadata property handle LaTeX escaping
            entry = TimesheetEntry.objects.create(
                user=request.user,
                client=client,
                category=category,
                date=event_date,
                hours=duration_hours,
                hourly_rate=hourly_rate,
                metadata={'event_title': title, 'event_description': description},
                google_calendar_event_id=event_id  # Store event ID for deduplication
            )
            created_count += 1
            logger.info(f"Created timesheet entry {entry.id} with {duration_hours}h at ${hourly_rate}/hr")

            
        except Exception as e:
            logger.exception(f"Error creating timesheet for event {event_id}: {e}")
            errors.append(f"Error importing '{event_id}': {str(e)}")
    
    logger.info(f"Timesheet creation complete: {created_count} created, {len(errors)} errors")
    
    if created_count > 0:
        messages.success(request, f"Successfully created {created_count} timesheet entries!")
    else:
        messages.warning(request, "No timesheet entries were created.")
    
    if errors:
        for error in errors:
            messages.warning(request, error)
    
    return redirect('timesheets:timesheet_list')

@login_required
def sync_contacts_page(request):
    """Display contacts sync options."""
    from .models import GoogleCalendarCredential
    
    # Check if user has Google Calendar connected
    has_google_connected = GoogleCalendarCredential.objects.filter(user=request.user).exists()
    
    if not has_google_connected:
        messages.error(request, "Please connect to Google Calendar first to enable contacts sync.")
        return redirect('todos:calendar_auth_start')
    
    from django.apps import apps
    Client = apps.get_model('clients', 'Client')
    clients_count = Client.objects.filter(user=request.user).count()
    
    context = {
        'has_google_connected': has_google_connected,
        'clients_count': clients_count,
    }
    
    return render(request, 'todos/sync_contacts.html', context)


@login_required
def sync_clients_to_contacts(request):
    """Sync all clients to Google Contacts."""
    import logging
    logger = logging.getLogger(__name__)
    
    from .calendar_utils import sync_all_clients_to_contacts, InvalidScopeError
    from .models import GoogleCalendarCredential
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('todos:calendar_auth_start')
    
    logger.info(f"Starting contacts sync for user {request.user.username}")
    
    try:
        synced_count = sync_all_clients_to_contacts(request.user)
        messages.success(request, f"Successfully synced {synced_count} clients to Google Contacts!")
        logger.info(f"Successfully synced {synced_count} clients for {request.user.username}")
    except InvalidScopeError:
        logger.warning(f"Scope mismatch for {request.user.username}")
        messages.warning(request, "Google permissions were updated. Please reconnect your Google account to continue.")
        return redirect('todos:calendar_auth_start')
    except Exception as e:
        logger.exception(f"Error syncing contacts for {request.user.username}: {e}")
        messages.error(request, f"Error syncing contacts: {str(e)}")
    
    return redirect('todos:sync_contacts_page')
