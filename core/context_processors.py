# core/context_processors.py

from decimal import Decimal


def vat_settings(request):
    """
    Makes the user's VAT registration status and rate 
    globally available in templates.
    """
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile:
            return {
                'GLOBAL_VAT_RATE': profile.vat_rate,
                'IS_VAT_REGISTERED': profile.is_vat_registered,
            }
    
    # Fallback for anonymous users or missing profiles
    return {
        'GLOBAL_VAT_RATE': Decimal('15.00'),
        'IS_VAT_REGISTERED': False,
    }

def currency_settings(request):
    """
    Makes the user's preferred currency symbol available in all templates.
    """
    if request.user.is_authenticated:
        # Accessing the currency from the user's profile
        # Adjust 'profile' if your related_name is different
        try:
            user_currency = request.user.profile.currency
        except AttributeError:
            user_currency = 'R' # Fallback
    else:
        user_currency = 'R' # Fallback for anonymous users

    return {
        'GLOBAL_CURRENCY': user_currency
    }