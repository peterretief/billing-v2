
# Create your tests here.
import os

from django.conf import settings
from django.test import TestCase


class AssetsTestCase(TestCase):
    def test_static_assets_are_localized(self):
        """Verify that all critical JS/CSS files exist in the static root."""
        required_files = [
            'js/htmx.min.js',
            'css/bootstrap.min.css',
            # Add others as you localize them
        ]
        
        for file_path in required_files:
            # We check STATICFILES_DIRS in dev or STATIC_ROOT in prod
            # This logic checks both to be safe
            found = False
            for loc in settings.STATICFILES_DIRS:
                if os.path.exists(os.path.join(loc, file_path)):
                    found = True
                    break
            
            if not found and settings.STATIC_ROOT:
                if os.path.exists(os.path.join(settings.STATIC_ROOT, file_path)):
                    found = True

            self.assertTrue(found, f"CRITICAL: {file_path} is missing from local static folders!")