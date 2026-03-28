from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from timesheets.forms import TimesheetEntryForm
from timesheets.models import WorkCategory

from .forms import EventForm
from .models import Event


class EventListView(LoginRequiredMixin, ListView):
    """Display all events for the current user."""
    model = Event
    template_name = 'events/event_list.html'
    context_object_name = 'events'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Event.objects.filter(user=self.request.user).select_related('client')
        
        # Always exclude cancelled events and events with processed/invoiced timesheets
        queryset = queryset.exclude(status='cancelled')
        queryset = queryset.exclude(timesheet_entries__is_billed=True).distinct()
        
        # Default to today and future events (show all if explicitly requested)
        today = self.request.GET.get('today', 'true')  # Defaults to 'true'
        if today != 'false':
            today_date = timezone.now().date()
            # Show today AND future dates (not just today)
            queryset = queryset.filter(due_date__gte=today_date)
        
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
        context['statuses'] = Event.Status.choices
        context['priorities'] = Event.Priority.choices
        context['clients'] = self.request.user.client_related.all()
        
        # Add current filters for template
        context['current_status'] = self.request.GET.get('status', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['current_client'] = self.request.GET.get('client', '')
        context['search_query'] = self.request.GET.get('search', '')
        context['today_filter'] = self.request.GET.get('today', 'true') != 'false'  # Default is true
        context['today_date'] = timezone.now().date()
        
        # Check if user has Google Calendar connected
        from .models import GoogleCalendarCredential
        try:
            cred = GoogleCalendarCredential.objects.get(user=self.request.user)
            context['google_calendar_connected'] = True
            context['google_email'] = cred.email_address
        except GoogleCalendarCredential.DoesNotExist:
            context['google_calendar_connected'] = False
            context['google_email'] = None
        
        return context


class EventCreateView(LoginRequiredMixin, CreateView):
    """Create a new event."""
    model = Event
    form_class = EventForm
    template_name = 'events/event_form.html'
    success_url = reverse_lazy('events:event_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = WorkCategory.objects.filter(user=self.request.user).order_by('name')
        return context
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        
        # Add helpful message based on due_date
        if form.instance.due_date:
            today = timezone.now().date()
            if form.instance.due_date != today:
                messages.success(
                    self.request, 
                    f"✓ Event created for {form.instance.due_date.strftime('%A, %b %d')}! (Click 'All' to view events outside today)"
                )
            else:
                messages.success(self.request, "✓ Event created successfully!")
        else:
            messages.success(self.request, "✓ Event created successfully!")
        
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class EventDetailView(LoginRequiredMixin, DetailView):
    """Display event details."""
    model = Event
    template_name = 'events/event_detail.html'
    context_object_name = 'event'
    
    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get linked timesheets
        context['linked_timesheets'] = self.object.timesheet_entries.select_related('client', 'category')
        
        # Check if a timesheet already exists for this event
        context['has_timesheet'] = self.object.timesheet_entries.exists()
        context['linked_timesheet'] = self.object.timesheet_entries.first()
        
        # Get the event's category
        matching_category = self.object.category
        
        # Add timesheet form with pre-filled initial data
        initial_data = {
            'client': self.object.client.id,
            'hourly_rate': self.object.client.default_hourly_rate,
            'hours': self.object.estimated_hours,
            'date': timezone.now().date(),
            'event': self.object.id,
        }
        if matching_category:
            initial_data['category'] = matching_category.id
            
        context['timesheet_form'] = TimesheetEntryForm(initial=initial_data, user=self.request.user)
        context['categories'] = WorkCategory.objects.filter(user=self.request.user)
        context['clients'] = self.request.user.client_related.all()
        # Pre-select the category for the form
        context['pre_selected_category_id'] = matching_category.id if matching_category else None
        
        return context


class EventUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing event."""
    model = Event
    form_class = EventForm
    template_name = 'events/event_form.html'
    
    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)
    
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
                    messages.info(request, "Timesheet deleted. You can now edit the event.")
                    return self.get(request, *args, **kwargs)
        
        # Check if trying to submit form while timesheet is linked
        linked_timesheet = self.object.timesheet_entries.first()
        if linked_timesheet and not unlink_timesheet:
            messages.error(request, "Cannot edit this event while a timesheet is linked. Please unlink it first.")
            return self.get(request, *args, **kwargs)
        
        return super().post(request, *args, **kwargs)
    
    def get_success_url(self):
        return reverse_lazy('events:event_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, "Event updated!")
        return super().form_valid(form)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class EventDeleteView(LoginRequiredMixin, DeleteView):
    """Delete an event."""
    model = Event
    template_name = 'events/event_confirm_delete.html'
    success_url = reverse_lazy('events:event_list')
    
    def get_queryset(self):
        return Event.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        event = self.get_object()
        event_name = event.category.name if event.category else "Uncategorized"
        messages.success(request, f"Event '{event_name}' deleted!")
        return super().delete(request, *args, **kwargs)


@login_required
def mark_event_completed(request, pk):
    """Mark an event as completed."""
    event = get_object_or_404(Event, pk=pk, user=request.user)
    try:
        event.mark_completed()
        event_name = event.category.name if event.category else "Uncategorized"
        messages.success(request, f"Event '{event_name}' marked as completed!")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('events:event_detail', pk=pk)


@login_required
def mark_event_cancelled(request, pk):
    """Mark an event as cancelled."""
    event = get_object_or_404(Event, pk=pk, user=request.user)
    try:
        event.mark_cancelled()
        event_name = event.category.name if event.category else "Uncategorized"
        messages.success(request, f"Event '{event_name}' cancelled!")
        return redirect('events:event_list')
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('events:event_detail', pk=pk)

@login_required
def calendar_auth_start(request):
    """Initiate Google Calendar OAuth flow."""
    import logging

    from django.conf import settings

    from .calendar_utils import get_oauth_flow
    
    logger = logging.getLogger(__name__)
    
    # Check if credentials are configured
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        messages.error(
            request,
            "Google Calendar is not configured. Please contact your administrator to set up OAuth credentials."
        )
        return redirect('events:event_list')
    
    try:
        flow = get_oauth_flow()
        
        # Generate authorization URL with prompt='consent' to force refresh token
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )
        
        # Store state, code_verifier, AND username in session for verification
        request.session['oauth_state'] = state
        request.session['code_verifier'] = flow.code_verifier
        request.session['oauth_user'] = request.user.username  # Store username to verify on callback
        request.session.modified = True
        request.session.save()  # Explicitly save the session
        
        logger.info(f"Started OAuth flow for {request.user.username}. State: {state}")
        
        return redirect(authorization_url)
    except Exception as e:
        logger.exception(f"Error initiating Google Calendar auth: {str(e)}")
        messages.error(request, f"Error initiating Google Calendar auth: {str(e)}")
        return redirect('events:event_list')


@login_required
def calendar_auth_callback(request):
    """Handle Google Calendar OAuth callback."""
    import logging
    from datetime import datetime, timezone

    from .calendar_utils import get_oauth_flow
    from .models import GoogleCalendarCredential
    
    logger = logging.getLogger(__name__)
    
    # CRITICAL: Verify that the current user matches the one who started the OAuth flow
    oauth_user_started = request.session.get('oauth_user')
    current_user = request.user.username
    
    if oauth_user_started and oauth_user_started != current_user:
        error_msg = f"OAuth mismatch: Flow started as '{oauth_user_started}' but callback received as '{current_user}'. Session may have been compromised or browser context switched. Please try again."
        logger.error(error_msg)
        messages.error(request, "Authentication error: Please log in again and retry the Google Calendar connection.")
        # Clear the stale OAuth session data
        request.session.pop('oauth_state', None)
        request.session.pop('code_verifier', None)
        request.session.pop('oauth_user', None)
        request.session.modified = True
        return redirect('events:event_list')
    
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
        request.session.pop('oauth_user', None)
        request.session.modified = True
        return redirect('events:event_list')
    
    # Get authorization code
    code = request.GET.get('code')
    if not code:
        error = request.GET.get('error', 'Unknown error')
        messages.error(request, f"Authorization cancelled: {error}")
        logger.error(f"No authorization code received for {request.user.username}. Error: {error}")
        request.session.pop('oauth_user', None)
        request.session.modified = True
        return redirect('events:event_list')
    
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
        
        # Get the user's email from Google Calendar API
        google_email = None
        try:
            from googleapiclient.discovery import build
            service = build('calendar', 'v3', credentials=creds)
            calendar = service.calendars().get(calendarId='primary').execute()
            google_email = calendar.get('id')
            logger.info(f"Retrieved Google email: {google_email}")
        except Exception as e:
            logger.warning(f"Could not retrieve email from Google: {e}")
        
        # Save credentials to database
        cred_obj, created = GoogleCalendarCredential.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': creds.token or '',
                'refresh_token': creds.refresh_token or '',
                'token_expiry': datetime.fromtimestamp(creds.expiry.timestamp(), tz=timezone.utc) if creds.expiry else None,
                'sync_enabled': True,
                'calendar_id': 'primary',
                'email_address': google_email,
            }
        )
        
        logger.info(f"Saved credentials: access_token={'set' if cred_obj.access_token else 'empty'}, refresh_token={'set' if cred_obj.refresh_token else 'empty'}")
        
        action = "updated" if not created else "created"
        logger.info(f"Google Calendar credential {action} for {request.user.username}")
        
        # Clean up session
        request.session.pop('oauth_state', None)
        request.session.pop('code_verifier', None)
        request.session.pop('oauth_user', None)
        request.session.modified = True
        request.session.save()
        
        messages.success(request, "Google Calendar connected successfully! You now have permission to access Calendar.")
        return redirect('events:event_list')
        
    except Exception as e:
        logger.exception(f"Error during OAuth callback for {request.user.username}: {str(e)}")
        # Clean up stale OAuth session data
        request.session.pop('oauth_state', None)
        request.session.pop('code_verifier', None)
        request.session.pop('oauth_user', None)
        request.session.modified = True
        messages.error(request, f"Error connecting to Google Calendar: {str(e)}")
        return redirect('events:event_list')


@login_required
def sync_events_to_calendar(request):
    """Sync all events to Google Calendar."""
    from .calendar_utils import InvalidScopeError, sync_all_events_to_calendar
    from .models import Event, GoogleCalendarCredential
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('events:calendar_auth_start')
    
    try:
        # Count unsynced events before sync
        unsynced = Event.objects.filter(user=request.user).exclude(status='cancelled').filter(
            due_date__isnull=False, synced_to_calendar=False
        ).count()
        
        synced_count = sync_all_events_to_calendar(request.user)
        
        if synced_count > 0:
            if unsynced > 0:
                messages.success(request, f"✓ Synced {synced_count} events to Google Calendar! {synced_count} are now marked as processed.")
            else:
                messages.info(request, f"ℹ Updated {synced_count} existing calendar events.")
        else:
            messages.info(request, "ℹ All events with due dates are already synced. Nothing new to push.")
    except InvalidScopeError:
        messages.warning(request, "Google permissions were updated. Please reconnect your Google account to continue.")
        return redirect('events:calendar_auth_start')
    
    return redirect('events:event_list')


@login_required
def import_calendar_events(request):
    """Display Google Calendar events to import as timesheets."""
    from datetime import datetime, timedelta, timezone

    from .calendar_utils import InvalidScopeError, get_google_calendar_service
    from .models import GoogleCalendarCredential
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('events:calendar_auth_start')
    
    try:
        service = get_google_calendar_service(request.user)
    except InvalidScopeError:
        messages.warning(request, "Google permissions were updated. Please reconnect your Google account to continue.")
        return redirect('events:calendar_auth_start')
    
    if not service:
        messages.error(request, "Could not access Google Calendar. Please reconnect.")
        return redirect('events:event_list')
    
    # Get date range from request or default to last 7 days and next 30 days
    days_back = request.GET.get('days_back', 30)  # Default to 30 days of past work
    try:
        days_back = int(days_back)
    except (ValueError, TypeError):
        days_back = 30
    
    # Check if user wants to see synced events
    show_synced = request.GET.get('show_synced', False)
    
    now = datetime.now(tz=timezone.utc)
    start_date = now - timedelta(days=days_back)
    end_date = now  # Only query up to now (past events only)
    
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
        
        # Filter to only show events that have already ended (can't invoice future work)
        past_events = []
        future_events = []
        
        for event in all_events:
            # Get event end time
            end_time = None
            
            if 'dateTime' in event.get('end', {}):
                # Timed event
                end_time_str = event['end']['dateTime']
                # Parse ISO format datetime
                if end_time_str.endswith('Z'):
                    end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                else:
                    end_time = datetime.fromisoformat(end_time_str)
            elif 'date' in event.get('end', {}):
                # All-day event - treat as ending at end of that day
                end_date_str = event['end']['date']
                try:
                    end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    end_time = end_date_obj.replace(hour=23, minute=59, second=59)
                except ValueError:
                    end_time = now
            else:
                end_time = now
            
            # Categorize event based on end time
            if end_time <= now:
                past_events.append(event)
            else:
                future_events.append(event)
        
        # Build a consolidated summary of filtered events
        future_count = len(future_events)
        
        # Filter out synced events (marked with [Synced] prefix) unless user wants to see them
        if show_synced:
            events = past_events
            synced_count = 0
        else:
            events = [e for e in past_events if not e.get('summary', '').startswith('[Synced]')]
            synced_count = len([e for e in past_events if e.get('summary', '').startswith('[Synced]')])
        
        # Show single consolidated message if there are filtered events
        if future_count > 0 or synced_count > 0:
            filtered_items = []
            if future_count > 0:
                filtered_items.append(f"⏳ {future_count} future event(s)")
            if synced_count > 0:
                filtered_items.append(f"🔄 {synced_count} already synced")
            
            if filtered_items:
                summary = "Hiding: " + ", ".join(filtered_items) + "."
                messages.info(request, summary)
        
    except Exception as e:
        messages.error(request, f"Error fetching calendar events: {str(e)}")
        events = []
    
    # Parse event titles and extract client/category suggestions
    import logging

    from clients.models import Client
    from timesheets.models import TimesheetEntry, WorkCategory
    logger = logging.getLogger(__name__)
    
    # Get work categories and clients for the user
    categories = WorkCategory.objects.filter(user=request.user).order_by('name')
    clients = Client.objects.filter(user=request.user).order_by('name')
    

    
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
        event['match_strategy'] = None
        location = event.get('location', '')
        organizer_info = event.get('organizer', {})
        organizer_email = organizer_info.get('email', '')
        
        logger.info(f"Processing event: {title}")
        logger.info(f"  Location: {location}, Organizer: {organizer_email}")
        
        # Strategy 0: Match by client name found in location (quick check) - PRIORITY 1
        if location and not event['suggested_client_id']:
            for client in clients:
                # Check if client name appears in location (case-insensitive)
                if client.name.lower() in location.lower():
                    event['suggested_client_id'] = client.id
                    event['suggested_client'] = client.name
                    event['match_strategy'] = 'location_name'
                    logger.info(f"  ✓ Matched by client name in location to: {client.name} (ID: {client.id})")
                    # CLEAR embedded client details since we found a location match
                    event['client_details'] = {}
                    break
        
        # Strategy 2: Match by location address - PRIORITY 2
        if location and not event['suggested_client_id']:
            for client in clients:
                if client.address and location.lower() in client.address.lower():
                    event['suggested_client_id'] = client.id
                    event['suggested_client'] = client.name
                    event['match_strategy'] = 'location_address'
                    logger.info(f"  ✓ Matched by address to client: {client.name} (ID: {client.id})")
                    # CLEAR embedded client details since we found a location match
                    event['client_details'] = {}
                    break
        
        # Strategy 5: Match by client name from title
        if not event['suggested_client_id'] and event.get('suggested_client'):
            for client in clients:
                if client.name.lower() == event['suggested_client'].lower():
                    event['suggested_client_id'] = client.id
                    event['match_strategy'] = 'title_name'
                    logger.info(f"  ✓ Matched by name from title to client: {client.name} (ID: {client.id})")
                    break
        
        if event['suggested_client_id']:
            logger.info(f"  Final suggested_client_id: {event['suggested_client_id']} (type: {type(event['suggested_client_id']).__name__})")
        else:
            logger.info("  No client match found for event")
        
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
        'categories': categories,
        'clients': clients,
        'show_synced': show_synced,
        'hide_imported': hide_imported,
    }
    
    return render(request, 'events/import_calendar_events.html', context)


@login_required
def create_timesheets_from_events(request):
    """Create timesheet entries from selected calendar events."""
    import logging
    from datetime import datetime, timezone

    from timesheets.models import TimesheetEntry, WorkCategory

    from .calendar_utils import get_google_calendar_service
    from .models import GoogleCalendarCredential
    
    logger = logging.getLogger(__name__)
    
    logger.info("=== CREATE_TIMESHEETS_FROM_EVENTS START ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"User: {request.user}")
    
    if request.method != 'POST':
        logger.info("Not a POST request, redirecting to import_calendar_events")
        return redirect('events:import_calendar_events')
    
    logger.info(f"POST data keys: {list(request.POST.keys())}")
    logger.info(f"POST data: {dict(request.POST)}")
    
    # Check if user has Google Calendar connected
    try:
        GoogleCalendarCredential.objects.get(user=request.user)
    except GoogleCalendarCredential.DoesNotExist:
        messages.error(request, "Please connect to Google Calendar first.")
        return redirect('events:calendar_auth_start')
    
    service = get_google_calendar_service(request.user)
    if not service:
        messages.error(request, "Could not access Google Calendar.")
        return redirect('events:import_calendar_events')
    
    # Get selected events from POST
    selected_events = request.POST.getlist('events[]')
    
    logger.info("=== SELECTED EVENTS DEBUG ===")
    logger.info(f"Total POST keys: {list(request.POST.keys())}")
    logger.info(f"All events[] values: {request.POST.getlist('events[]')}")
    logger.info(f"Selected events count: {len(selected_events)}")
    logger.info(f"Selected events: {selected_events}")
    
    if not selected_events:
        logger.warning("No events selected")
        messages.error(request, "Please select at least one event.")
        return redirect('events:import_calendar_events')
    
    # Validate that each selected event has a category and client assigned
    from clients.models import Client
    
    event_configs = {}  # Store category and client for each event
    for event_id in selected_events:
        logger.info(f"Validating event: {event_id}")
        category_id = request.POST.get(f'category_id_{event_id}')
        client_id = request.POST.get(f'client_id_{event_id}')
        
        logger.info(f"  Event {event_id}: category_id={category_id}, client_id={client_id}")
        
        if not client_id:
            logger.error(f"VALIDATION FAILED - Event {event_id}: missing client ({client_id})")
            messages.error(request, f"Event {event_id}: Please select a client.")
            return redirect('events:import_calendar_events')
        
        # Handle category - either use existing or auto-create
        category = None
        
        # Check if this is a "create new" marker (from suggested category in dropdown)
        if category_id and category_id.startswith('create_new_'):
            logger.info("  'Create new' category marker detected")
            category_id = None  # Treat as empty so it falls through to auto-create
        
        if category_id:
            try:
                category = WorkCategory.objects.get(id=category_id, user=request.user)
                logger.info(f"  Found existing category: {category.name}")
            except WorkCategory.DoesNotExist:
                logger.warning(f"Category {category_id} not found, will try auto-create")
        
        # If no category found or no ID provided, try to auto-create from suggested name
        if not category:
            suggested_category_name = request.POST.get(f'suggested_category_{event_id}', '').strip()
            if suggested_category_name:
                # Try to find existing category by name
                category, created = WorkCategory.objects.get_or_create(
                    user=request.user,
                    name=suggested_category_name,
                    defaults={'metadata_schema': ['description']}
                )
                if created:
                    logger.info(f"  Auto-created new category: {category.name} with description metadata")
                    messages.success(request, f"Auto-created new work category: '{suggested_category_name}'")
                else:
                    logger.info(f"  Found existing category by name: {category.name}")
            else:
                logger.error(f"VALIDATION FAILED - Event {event_id}: no category selected and no suggested category name")
                messages.error(request, f"Event {event_id}: Please select a work category.")
                return redirect('events:import_calendar_events')
        
        if not category:
            logger.error(f"VALIDATION FAILED - Event {event_id}: could not determine category")
            messages.error(request, f"Event {event_id}: Could not determine work category.")
            return redirect('events:import_calendar_events')
        
        # Validate client
        try:
            client = Client.objects.get(id=client_id, user=request.user)
        except Client.DoesNotExist:
            logger.error(f"Client {client_id} not found")
            messages.error(request, f"Invalid client selected for event {event_id}.")
            return redirect('events:import_calendar_events')
        
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
                    logger.info("All-day event: using default 8 hours")
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
            
            # IMPORTANT: Validate completion gate - only create timesheet if calendar event has ended
            from django.utils import timezone
            now_tz = timezone.now()
            
            # Check if the calendar event has actually ended
            calendar_event_ended = False
            start_time = event.get('start', {})
            end_time_obj = event.get('end', {})
            
            # Parse end time from calendar event
            if 'dateTime' in end_time_obj:
                end_time_str = end_time_obj['dateTime']
                try:
                    if end_time_str.endswith('Z'):
                        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                    else:
                        end_time = datetime.fromisoformat(end_time_str)
                    calendar_event_ended = end_time <= now_tz
                except Exception as e:
                    logger.warning(f"Could not parse end time for event {event_id}: {e}")
            elif 'date' in end_time_obj:
                # All-day event - treat as ended if today or in past
                end_date_str = end_time_obj['date']
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    calendar_event_ended = end_date <= now_tz
                except Exception as e:
                    logger.warning(f"Could not parse end date for event {event_id}: {e}")
            
            if not calendar_event_ended:
                logger.warning(f"Calendar event {event_id} hasn't completed yet. Skipping.")
                errors.append(f"'{title}' - Calendar event hasn't finished yet. Only completed calendar events can be imported.")
                continue
            
            # Create timesheet entry (prevent duplicates by checking google_calendar_event_id)
            # Use get_or_create to avoid duplicates if the same calendar event is imported twice
            entry, created = TimesheetEntry.objects.get_or_create(
                user=request.user,
                google_calendar_event_id=event_id,  # Use event ID as unique key
                defaults={
                    'client': client,
                    'category': category,
                    'date': event_date,
                    'hours': duration_hours,
                    'hourly_rate': hourly_rate,
                    'metadata': {'event_title': title, 'event_description': description},
                }
            )
            
            if created:
                created_count += 1
                logger.info(f"Created new timesheet entry {entry.id} with {duration_hours}h at ${hourly_rate}/hr")
                
                # Auto-mark the corresponding app Event as complete ONLY if calendar event has ended
                from .models import Event
                if calendar_event_ended:  # Only if event date has passed
                    try:
                        app_event = Event.objects.get(
                            user=request.user,
                            google_calendar_event_id=event_id
                        )
                        if not app_event.is_completed:
                            app_event.mark_completed()
                            logger.info(f"Auto-marked event {app_event.id} as complete")
                    except Event.DoesNotExist:
                        logger.info(f"No corresponding app event found for calendar event {event_id}, skipping auto-completion")
                    except Exception as e:
                        logger.warning(f"Could not auto-mark event as complete: {e}")
                else:
                    logger.info(f"Calendar event {event_id} is in future, skipping auto-completion")
            else:
                logger.info(f"Timesheet entry {entry.id} already exists for event {event_id}, skipping")

            
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
def find_available_slots_api(request):
    """
    AJAX endpoint to find available calendar slots.
    
    Expected POST parameters:
    - duration_hours: float (duration of the event in hours)
    - num_slots: int (number of slots to find, default 5)
    - days_ahead: int (how many days ahead to search, default 30)
    
    Returns JSON:
    {
        'success': bool,
        'slots': [
            {'start': datetime_str, 'end': datetime_str, 'display': readable_str},
            ...
        ],
        'error': error_message (if success=False)
    }
    """
    import json
    import logging

    from django.http import JsonResponse

    from .calendar_utils import find_available_slots
    
    logger = logging.getLogger(__name__)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST requests allowed'}, status=405)
    
    try:
        # Parse request data
        data = json.loads(request.body)
        duration_hours = float(data.get('duration_hours', 1))
        num_slots = int(data.get('num_slots', 5))
        days_ahead = int(data.get('days_ahead', 30))
        
        # Validate inputs
        if duration_hours <= 0 or duration_hours > 8:
            return JsonResponse({'success': False, 'error': 'Duration must be between 0 and 8 hours'})
        
        if num_slots <= 0 or num_slots > 20:
            return JsonResponse({'success': False, 'error': 'Number of slots must be between 1 and 20'})
        
        if days_ahead <= 0 or days_ahead > 90:
            return JsonResponse({'success': False, 'error': 'Days ahead must be between 1 and 90'})
        
        # Convert hours to minutes
        duration_minutes = int(duration_hours * 60)
        
        # Find available slots
        slots = find_available_slots(
            user=request.user,
            duration_minutes=duration_minutes,
            num_slots=num_slots,
            days_ahead=days_ahead
        )
        
        if not slots:
            return JsonResponse({
                'success': False,
                'error': 'No available slots found. Try extending the search period.',
                'slots': []
            })
        
        # Format slots for display
        formatted_slots = []
        for start_dt, end_dt in slots:
            formatted_slots.append({
                'start': start_dt.isoformat(),
                'end': end_dt.isoformat(),
                'display': start_dt.strftime('%a, %b %d at %I:%M %p'),  # e.g., "Mon, Mar 10 at 02:00 PM"
                'date_only': start_dt.date().isoformat(),  # For due_date field
            })
        
        logger.info(f"Found {len(formatted_slots)} slots for {request.user.username} with {duration_minutes} min duration")
        
        return JsonResponse({
            'success': True,
            'slots': formatted_slots,
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON in request body'}, status=400)
    except ValueError as e:
        return JsonResponse({'success': False, 'error': f'Invalid input: {str(e)}'}, status=400)
    except Exception as e:
        logger.exception(f"Error finding available slots for {request.user.username}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred while finding slots'}, status=500)
    