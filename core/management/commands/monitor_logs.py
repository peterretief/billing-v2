import sys
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Monitor logs for errors and send alerts'

    def handle(self, *args, **options):
        # Import and run the monitor
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from log_monitor import LogMonitor

        monitor = LogMonitor()
        exit_code = monitor.run()
        
        if exit_code != 0:
            self.stderr.write(self.style.ERROR(f'Monitoring failed with code {exit_code}'))
        else:
            self.stdout.write(self.style.SUCCESS('Monitoring completed successfully'))

        sys.exit(exit_code)
