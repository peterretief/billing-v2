# Temporary Files Cleanup System

This directory contains scripts to automatically clean up temporary LaTeX and PDF files generated during invoice and timesheet report generation.

## Files

- `core/management/commands/cleanup_tmp_files.py` - Django management command
- `cleanup_tmp_files_cron.sh` - Cron job wrapper script

## What Gets Cleaned

The cleanup process safely removes:
- `report_*.pdf` - Generated invoice and timesheet PDFs
- `report_*.tex` - LaTeX source files
- `report_*.log` - LaTeX compilation logs
- `report_*.aux` - LaTeX auxiliary files

**Preserved:**
- `email_status.log` - Email delivery tracking (important audit trail)
- Database records - All invoice LaTeX and timesheet data remain in database

## Usage

### Manual Cleanup

```bash
# Preview what would be deleted (dry run)
python manage.py cleanup_tmp_files --dry-run

# Delete all report files
python manage.py cleanup_tmp_files

# Delete only files older than 7 days
python manage.py cleanup_tmp_files --days-old 7

# Delete only files older than 30 days
python manage.py cleanup_tmp_files --days-old 30
```

### Automatic Cleanup (Cron Job)

#### Setup (one-time)

```bash
chmod +x /opt/billing_v2/cleanup_tmp_files_cron.sh
crontab -e
```

#### Add One of These Lines to Crontab

**Monthly (1st day of month at 2 AM):**
```
0 2 1 * * /opt/billing_v2/cleanup_tmp_files_cron.sh
```

**Weekly (every Sunday at 2 AM):**
```
0 2 * * 0 /opt/billing_v2/cleanup_tmp_files_cron.sh
```

**Daily (every day at 2 AM):**
```
0 2 * * * /opt/billing_v2/cleanup_tmp_files_cron.sh
```

#### View Current Cron Jobs

```bash
crontab -l
```

#### View Cleanup Logs

```bash
tail -f /opt/billing_v2/tmp/cleanup.log
```

## How Regeneration Works

Since all invoice LaTeX content is stored in the database, PDFs can be instantly recreated:

1. **Invoice PDFs:**
   - LaTeX stored in `invoices.Invoice.latex_content` field
   - PDFs regenerated on-demand when downloaded

2. **Timesheet Report PDFs:**
   - Timesheet data persisted in `timesheets.TimesheetEntry` records
   - PDFs regenerated from entry data when requested

## Storage Savings

**Current Temporary Files:**
- ~1.2 MB can be freed by cleanup
- PDFs: ~60-80 KB each
- LaTeX files: ~700 B to 1.3 KB each
- Logs and aux files: ~7-8 KB each

**No Data Loss:**
- All important data remains in database
- Files can be recreated instantly
- Safe to clean up regularly

## Troubleshooting

If cleanup fails:

1. Check cron logs:
   ```bash
   tail -f /opt/billing_v2/tmp/cleanup.log
   ```

2. Verify script permissions:
   ```bash
   ls -la /opt/billing_v2/cleanup_tmp_files_cron.sh
   ```

3. Test manually first:
   ```bash
   cd /opt/billing_v2 && source venv/bin/activate
   python manage.py cleanup_tmp_files --dry-run
   ```

4. Check if management command exists:
   ```bash
   python manage.py help cleanup_tmp_files
   ```
