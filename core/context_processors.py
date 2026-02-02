# core/context_processors.py

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