from django.apps import apps
import logging

logger = logging.getLogger(__name__)

class PluginManager:
    """Discovers and manages dynamic plugins across the system."""
    
    @staticmethod
    def get_available_plugins():
        """
        Scan all installed apps for those marked with 'is_plugin = True'.
        Returns a list of dicts with plugin metadata.
        """
        available = []
        for app_config in apps.get_app_configs():
            if getattr(app_config, 'is_plugin', False):
                available.append({
                    'app_label': app_config.label,
                    'name': app_config.name,
                    'display_name': getattr(app_config, 'plugin_display_name', app_config.verbose_name),
                    'description': getattr(app_config, 'plugin_description', ''),
                })
        return available

    @staticmethod
    def get_enabled_plugins(user):
        """
        Returns full metadata for plugins enabled for a specific user.
        """
        if not user.is_authenticated:
            return []
            
        try:
            enabled_labels = user.profile.enabled_plugins or []
            available = PluginManager.get_available_plugins()
            
            # Filter available plugins by what the user has enabled
            return [p for p in available if p['app_label'] in enabled_labels]
        except Exception as e:
            logger.error(f"Error fetching enabled plugins: {e}")
            return []
