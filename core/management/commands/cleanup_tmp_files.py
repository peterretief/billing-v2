import glob
import os
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Clean up temporary report files (PDF, LaTeX, logs, aux) from the tmp directory"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-old",
            type=int,
            default=0,
            help="Only delete files older than N days (default: delete all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        tmp_dir = os.path.join(settings.BASE_DIR, "tmp")

        if not os.path.exists(tmp_dir):
            self.stdout.write(self.style.WARNING(f"tmp directory does not exist: {tmp_dir}"))
            return

        dry_run = options["dry_run"]
        days_old = options["days_old"]
        cutoff_time = datetime.now() - timedelta(days=days_old) if days_old > 0 else None

        # Files to clean up (preserve email_status.log)
        patterns = [
            "report_*.pdf",
            "report_*.tex",
            "report_*.log",
            "report_*.aux",
        ]

        total_deleted = 0
        total_size = 0

        for pattern in patterns:
            file_glob = os.path.join(tmp_dir, pattern)
            files = glob.glob(file_glob)

            for filepath in files:
                # Skip if file is too recent
                if cutoff_time:
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_time > cutoff_time:
                        continue

                file_size = os.path.getsize(filepath)
                filename = os.path.basename(filepath)

                if dry_run:
                    self.stdout.write(self.style.WARNING(f"Would delete: {filename} ({self.format_size(file_size)})"))
                else:
                    try:
                        os.remove(filepath)
                        self.stdout.write(self.style.SUCCESS(f"Deleted: {filename} ({self.format_size(file_size)})"))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Failed to delete {filename}: {str(e)}"))
                        continue

                total_deleted += 1
                total_size += file_size

        # Summary
        self.stdout.write("\n" + "=" * 60)
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would delete {total_deleted} files, freeing {self.format_size(total_size)}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cleanup complete: Deleted {total_deleted} files, freed {self.format_size(total_size)}"
                )
            )

    def format_size(self, bytes):
        """Convert bytes to human-readable format"""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.1f} TB"
