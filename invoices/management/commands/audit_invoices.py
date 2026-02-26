"""
Management command to audit invoice reporting consistency.

Usage:
    python manage.py audit_invoices --user <username>
    python manage.py audit_invoices --all
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from invoices.audit import InvoiceAudit

User = get_user_model()


class Command(BaseCommand):
    help = "Audit invoice reporting consistency for one or all users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            help="Username to audit (leave blank to audit current user)"
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Audit all users"
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output results as JSON"
        )

    def handle(self, *args, **options):
        import json
        
        audit_all = options.get("all", False)
        username = options.get("user")
        json_output = options.get("json", False)
        
        if audit_all:
            users = User.objects.all()
        elif username:
            try:
                users = [User.objects.get(username=username)]
            except User.DoesNotExist:
                raise CommandError(f'User "{username}" not found')
        else:
            raise CommandError('Please specify --user <username> or use --all')
        
        results = []
        
        for user in users:
            self.stdout.write(f"\nAuditing {user.username}...")
            
            audit = InvoiceAudit(user)
            audit_result = audit.run_full_audit()
            results.append(audit_result)
            
            if json_output:
                self.stdout.write(json.dumps(audit_result, indent=2, default=str))
            else:
                self.stdout.write(audit.get_summary())
                
                if not audit_result['passed']:
                    for check_name, check_result in audit_result['checks'].items():
                        if not check_result.get('is_consistent', True):
                            self.stdout.write(
                                self.style.WARNING(f"\n{check_name} failed:")
                            )
                            for key, value in check_result.items():
                                self.stdout.write(f"  {key}: {value}")
        
        # Summary
        all_passed = all(r['passed'] for r in results)
        self.stdout.write("\n" + "="*50)
        if all_passed:
            self.stdout.write(self.style.SUCCESS("✓ All audits passed!"))
        else:
            self.stdout.write(self.style.ERROR("✗ Some audits failed!"))
            failed_count = sum(1 for r in results if not r['passed'])
            self.stdout.write(f"  {failed_count}/{len(results)} users have issues")
