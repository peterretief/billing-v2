# Calendar & Event Integration Rules

## Data Model Structure

```
Google Calendar Event
    ↓ (sync via calendar_utils)
    ↓
App Event Model
├─ calendar_start_time / calendar_end_time (read-only from calendar)
├─ status (backlog → todo → in_progress → completed)
├─ completed_at (timestamp when marked complete)
└─ synced_to_calendar (bidirectional sync flag)
    ↓ (only if completed)
    ↓
TimesheetEntry (todo FK to Event)
├─ date (when worked)
├─ hours (logged hours)
├─ is_billed (invoiced flag)
└─ google_calendar_event_id (dedup if imported from calendar)
```

---

## Integration Rules

### Rule 1: Completion Status (The Gate)

**Calendar completion** = When `calendar_end_time` is in the past (event duration finished)
**App completion** = `status = "completed"` + `completed_at` timestamp

**Enforcement:**
```python
# Event can only be linked to timesheet if:
def can_create_timesheet_entry(self):
    # 1. Calendar event must be finished (if synced from calendar)
    if self.calendar_end_time:
        import timezone
        if timezone.now() < self.calendar_end_time:
            return False, "Calendar event hasn't finished yet"
    
    # 2. App event must be marked completed
    if self.status != self.Status.COMPLETED:
        return False, f"Event status is {self.status}, must be completed"
    
    # 3. Not already invoiced
    if self.timesheet_entries.filter(invoice__isnull=False).exists():
        return False, "Already invoiced"
    
    return True, None
```

---

### Rule 2: Data Flow Direction (3 Scenarios)

#### **Scenario A: Calendar-First Events** (Most Common)
```
1. User creates event in Google Calendar
2. Celery sync task (every 5 min) pulls events
   - Checks google_calendar_event_id (deduplication)
   - Creates/updates app Event model
   - Sets calendar_start_time, calendar_end_time
   - Marks synced_to_calendar = true

3. When calendar event ends:
   - Sync check: if timezone.now() > calendar_end_time
   - Auto-mark app event as: status = "completed", completed_at = now()
   - Mark calendar_end_time as "source of truth"

4. User can then create timesheet entry
   - Timesheet references the Event via todo FK
   - Stores google_calendar_event_id for audit
   - Duration can be different from calendar (e.g., 2-hour meeting, 1.5 hours to bill)
```

#### **Scenario B: App-Created Events** (Manual Tasks)
```
1. User creates event in app (no calendar)
   - status = "todo"
   - estimated_hours set
   - No calendar_start/end_time yet

2. User manually marks status = "completed" when done
   - Sets completed_at = now()
   - estimated_hours → timesheet logging

3. User creates timesheet entry
   - Actual hours logged may differ from estimated_hours
   - Useful for manual/offline work
```

#### **Scenario C: Hybrid** (App Event + Calendar)
```
1. User has app event (scenario B)
2. Later creates calendar event
   - Sync pulls calendar event
   - Links via calendar_uuid or manual association
   - calendar_start/end_time now valid

3. Completion follows Calendar-First rules (scenario A)
   - Calendar end time becomes source of truth
   - Overrides manual estimated_hours if needed
```

---

### Rule 3: Linking Logic

**When creating a TimesheetEntry:**

```python
def create_timesheet_from_event(event, hours, date=None):
    """
    Create a timesheet entry from a completed event.
    """
    # Check completion gate (Rule 1)
    can_create, reason = event.can_create_timesheet_entry()
    if not can_create:
        raise ValidationError(f"Cannot create timesheet: {reason}")
    
    # If calendar event, preserve the source
    google_event_id = event.google_calendar_event_id
    
    # Create timesheet entry
    entry = TimesheetEntry(
        todo=event,  # Link to event
        google_calendar_event_id=google_event_id,  # Track calendar origin
        date=date or event.calendar_end_time.date(),
        hours=hours,  # User specifies actual billable hours
        hourly_rate=event.client.hourly_rate,
        category=event.category,  # Pre-fill from event
    )
    entry.save()
    
    return entry
```

---

### Rule 4: Completion Rules When Status Changes

**On mark_completed():**
```python
def mark_completed(self):
    """Mark event as completed."""
    
    # Check constraints
    if self.timesheet_entries.filter(is_billed=True).exists():
        raise ValueError("Cannot modify: has invoiced timesheet")
    
    self.status = self.Status.COMPLETED
    
    # Set completion time based on source
    if self.calendar_end_time:
        # Calendar event is source of truth
        self.completed_at = self.calendar_end_time
    else:
        # Manual completion
        self.completed_at = timezone.now()
    
    self.save()
```

**On mark_cancelled():**
```python
def mark_cancelled(self):
    """Cancel event - cascade rules."""
    
    # Check constraints
    if self.timesheet_entries.filter(is_billed=True).exists():
        raise ValueError("Cannot cancel: has invoiced timesheet")
    
    # Delete non-invoiced timesheets (maintain integrity)
    self.timesheet_entries.filter(is_billed=False).delete()
    
    self.status = self.Status.CANCELLED
    self.save()
```

---

### Rule 5: Sync Status Tracking

Track bidirectional sync with these fields:

```python
# Event model fields (already in your model)
last_synced_from = ['app', 'calendar']  # Where last update came from
sync_status = ['pending', 'synced', 'failed']  # Current sync state
last_synced_at = DateTimeField  # When last synced

# Logic: Priority during merge conflict
if event.last_synced_from == 'calendar' and calendar_event.updated > event.updated_at:
    # Calendar is newest → use calendar values
    event.calendar_start_time = calendar_event.start
    event.calendar_end_time = calendar_event.end
    event.last_synced_from = 'calendar'
elif event.last_synced_from == 'app' and event.updated_at > calendar_event.updated:
    # App is newest → push to calendar
    push_to_calendar(event)
    event.last_synced_from = 'app'
```

---

### Rule 6: Prevention of Modification After Invoicing

```python
def can_be_modified(self):
    """Prevent changes once invoiced."""
    return not self.timesheet_entries.filter(is_billed=True).exists()

# Enforce in views
if not event.can_be_modified():
    raise PermissionDenied("Cannot modify event with invoiced timesheet")
```

---

## Implementation Sequence

**Phase 1: Sync System** (Already working)
- ✅ Pull calendar events every 5 minutes
- ✅ Create/update app Events
- ✅ Set calendar_start_time, calendar_end_time
- ✅ Handle deduplication via google_calendar_event_id

**Phase 2: Completion Detection** (Add this)
- Add logic: When calendar_end_time passes, auto-mark event as completed
- Run in Celery task: `check_completed_calendar_events()` every 15 minutes
- Set completed_at to match calendar_end_time

**Phase 3: Timesheet Gating** (Add this)
- Add `can_create_timesheet_entry()` validation
- Show UI hint: "Complete the event before logging time"
- Only show "Create Timesheet" button if event.status == COMPLETED

**Phase 4: Invoice Protection** (Already partially done)
- ✅ Prevent modification of invoiced timesheets
- Add cascade on cancel: delete non-invoiced timesheets
- Audit: Log what was auto-cancelled

**Phase 5: Conflict Resolution** (Optional, now)
- Implement sync_status tracking
- Handle last_synced_from priority
- Alert user on conflicts

---

## Key Advantages

| Advantage | How It Works |
|---|---|
| **Single Source of Truth** | Calendar end_time is the authority for completion |
| **Audit Trail** | google_calendar_event_id + EventSyncLog tracks origin |
| **Invoice Safety** | Gate prevents modifications once billed |
| **Flexible Billing** | Timesheet hours ≠ calendar duration (e.g., 1-hour meeting, bill 0.5 hours prep) |
| **Automatic** | No manual status updates needed for calendar events |
| **Conflict-Free** | Bidirectional sync with clear priority rules |

---

## Database Queries to Add

```python
# Find events ready to log time for
Event.objects.filter(
    status='completed',
    timesheet_entries__isnull=True  # No timesheet yet
).distinct()

# Find events with incomplete logging
events = []
for event in Event.objects.filter(estimated_hours__isnull=False):
    logged = sum(e.hours for e in event.timesheet_entries.all())
    if logged < event.estimated_hours:
        events.append(event)
return events

# Find events pending calendar sync
Event.objects.filter(sync_status='pending')

# Check invoicing blocks
Event.objects.filter(
    timesheet_entries__invoice__isnull=False
).distinct()
```

---

## Edge Cases Handled

✅ Event marked completed before calendar event ends → Allow, but warn user  
✅ Calendar event updated after timesheet created → Update timesheet.date if needed  
✅ Event cancelled with unposted timesheet → Auto-delete timesheet  
✅ Manual event (no calendar) → Use user's manual completion  
✅ Calendar event deleted → App event remains, marked "sync failed"  
✅ Multiple timesheets for same event → Allow (e.g., 2-day event = 2 entries)
