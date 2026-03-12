#!/usr/bin/env python
"""
Lint script to verify Celery app configuration pattern.

Use in CI/CD pipeline to prevent Celery task autodiscovery failures:
- If an app has tasks.py, it MUST import tasks in apps.py ready() method

Run: python scripts/check_celery_app_configs.py
"""

import ast
import os
import sys


def check_app_config(app_path):
    """Check if app config properly imports tasks"""
    tasks_py = os.path.join(app_path, "tasks.py")
    apps_py = os.path.join(app_path, "apps.py")

    if not os.path.exists(tasks_py):
        return True, "No tasks.py"

    if not os.path.exists(apps_py):
        return False, "Has tasks.py but no apps.py"

    try:
        with open(apps_py, "r") as f:
            source = f.read()

        tree = ast.parse(source)

        # Look for ready() method
        ready_method = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "ready":
                ready_method = node
                break

        if not ready_method:
            return False, "Has tasks.py but ready() method not found in apps.py"

        # Check if ready() imports tasks
        has_import = False
        app_name = os.path.basename(app_path)

        # Check for: import <app>.tasks
        if f"import {app_name}.tasks" in source[ready_method.col_offset :]:
            has_import = True

        # Check for: from <app> import tasks
        if f"from {app_name} import tasks" in source[ready_method.col_offset :]:
            has_import = True

        # Check for: from <app>.tasks import <something>
        if f"from {app_name}.tasks import" in source[ready_method.col_offset :]:
            has_import = True

        if not has_import:
            return (
                False,
                f"ready() method doesn't import {app_name}.tasks. "
                f"Add to ready(): from {app_name} import tasks",
            )

        return True, "OK - ready() imports tasks"

    except SyntaxError as e:
        return False, f"Syntax error in apps.py: {e}"
    except Exception as e:
        return False, f"Error checking apps.py: {e}"


def main():
    """Check all Django apps for Celery task pattern compliance"""
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    apps_to_check = [
        "billing_schedule",
        "invoices", 
        "events",
        "clients",
        "notifications",
    ]

    print("Checking Celery app configuration pattern...\n")

    all_ok = True
    for app_name in apps_to_check:
        app_path = os.path.join(workspace_root, app_name)
        if not os.path.exists(app_path):
            print(f"⚠️  {app_name}: App not found")
            continue

        ok, message = check_app_config(app_path)
        
        if ok:
            print(f"✓ {app_name}: {message}")
        else:
            print(f"❌ {app_name}: {message}")
            all_ok = False

    print()
    if all_ok:
        print("✓ All Celery app configs OK")
        return 0
    else:
        print("❌ Some app configs need fixing")
        return 1


if __name__ == "__main__":
    sys.exit(main())
