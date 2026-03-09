#!/bin/bash
###############################################################################
# Celery Task Registration Verification
# 
# Run at application startup to verify all expected tasks are registered.
# Used by: supervisord, Docker, systemd, or manual startup
# 
# Exit codes:
#   0 = All tasks registered (healthy)
#   1 = Critical number of tasks missing (startup should fail)
#   2 = Warning: fewer tasks than expected (startup continues)
###############################################################################

set -e

WORKSPACE="/opt/billing_v2"
EXPECTED_TASK_COUNT=9
WARNING_THRESHOLD=8
CRITICAL_THRESHOLD=5

echo "Verifying Celery task registration..."

# Activate virtual environment
source "$WORKSPACE/venv/bin/activate"

# Run Python verification
python "$WORKSPACE/manage.py" shell << 'EOF'
from core_project.celery import app
import sys

# Count user tasks (exclude celery internal tasks)
tasks = [t for t in app.tasks.keys() if not t.startswith('celery.')]
print(f"Found {len(tasks)} Celery tasks")

# Print task list for debugging
for task in sorted(tasks):
    print(f"  - {task}")

# Exit with appropriate code
if len(tasks) < 5:
    print("\n❌ CRITICAL: Too few tasks found. Celery autodiscover appears broken!")
    sys.exit(1)
elif len(tasks) < 8:
    print(f"\n⚠️  WARNING: Only {len(tasks)} tasks (expected {9})")
    sys.exit(2)
else:
    print(f"\n✓ Task registration OK: {len(tasks)} tasks registered")
    sys.exit(0)
EOF

exit_code=$?

case $exit_code in
    0)
        echo "✓ Celery startup verification passed"
        exit 0
        ;;
    1)
        echo "❌ Celery startup verification FAILED - critical task loss"
        exit 1
        ;;
    2)
        echo "⚠️  Celery startup verification WARNING - reduced task count"
        exit 0  # Don't fail startup on warning
        ;;
    *)
        echo "❌ Error running Celery verification"
        exit 1
        ;;
esac
