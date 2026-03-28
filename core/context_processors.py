from .plugins import PluginManager

def vat_settings(request):
    """Provides VAT-related settings to templates."""
    if not request.user.is_authenticated:
        return {
            'IS_VAT_REGISTERED': False,
            'VAT_RATE': 15.00,
        }
    try:
        profile = request.user.profile
        return {
            'IS_VAT_REGISTERED': profile.is_vat_registered,
            'VAT_RATE': profile.vat_rate,
        }
    except Exception:
        return {
            'IS_VAT_REGISTERED': False,
            'VAT_RATE': 15.00,
        }

def currency_settings(request):
    """Provides currency settings to templates."""
    if not request.user.is_authenticated:
        return {'GLOBAL_CURRENCY': 'R'}
    try:
        return {'GLOBAL_CURRENCY': request.user.profile.currency}
    except Exception:
        return {'GLOBAL_CURRENCY': 'R'}

def enabled_plugins(request):
    """
    Makes the list of enabled plugins available globally in templates.
    Used for dynamic sidebar/menu rendering.
    """
    if not request.user.is_authenticated:
        return {'ENABLED_PLUGINS': []}
        
    return {
        'ENABLED_PLUGINS': PluginManager.get_enabled_plugins(request.user)
    }
