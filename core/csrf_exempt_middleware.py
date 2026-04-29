"""
Middleware to exempt specific API endpoints from CSRF protection.
This allows external systems (like MealShare) to call billing_v2 APIs.
"""
from django.middleware.csrf import CsrfViewMiddleware

class CSRFExemptAPIMiddleware(CsrfViewMiddleware):
    """Custom CSRF middleware that exempts API endpoints."""
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Exempt API endpoints from CSRF checks
        if request.path.startswith('/invoices/api/'):
            # Skip CSRF checks for API endpoints
            return None
        
        # For all other paths, use standard CSRF handling
        return super().process_view(request, view_func, view_args, view_kwargs)
