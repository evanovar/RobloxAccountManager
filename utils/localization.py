"""
Localization Module for Roblox Account Manager
Handles multi-language support with dynamic text loading
"""

import os
import json


class Localization:
    """Manages application localization and translations"""
    
    AVAILABLE_LANGUAGES = {
        "en_US": "English",
        "pt_BR": "Português (Brasil)",
        "es_ES": "Español"
    }
    
    def __init__(self, language="en_US"):
        """Initialize localization with specified language"""
        self.current_language = language
        self.translations = {}
        self.locales_folder = "locales"
        
        # Create locales folder if it doesn't exist
        if not os.path.exists(self.locales_folder):
            os.makedirs(self.locales_folder)
        
        self.load_language(language)
    
    def load_language(self, language):
        """Load translations for specified language"""
        locale_file = os.path.join(self.locales_folder, f"{language}.json")
        
        if not os.path.exists(locale_file):
            # Fallback to English if language file not found
            language = "en_US"
            locale_file = os.path.join(self.locales_folder, f"{language}.json")
        
        try:
            with open(locale_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
            self.current_language = language
        except Exception as e:
            print(f"Error loading language file: {e}")
            # Load default empty translations
            self.translations = {}
    
    def get(self, key_path, **kwargs):
        """
        Get translated text by key path
        
        Args:
            key_path: Dot-separated path to translation key (e.g., 'buttons.add_account')
            **kwargs: Format arguments for string formatting
        
        Returns:
            Translated and formatted string
        """
        keys = key_path.split('.')
        value = self.translations
        
        # Navigate through nested dictionary
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                # Return key if translation not found
                return f"[{key_path}]"
        
        # Format string if kwargs provided
        if kwargs and isinstance(value, str):
            try:
                return value.format(**kwargs)
            except KeyError:
                return value
        
        return value
    
    def set_language(self, language):
        """Change current language"""
        if language in self.AVAILABLE_LANGUAGES:
            self.load_language(language)
            return True
        return False
    
    def get_current_language(self):
        """Get current language code"""
        return self.current_language
    
    def get_current_language_name(self):
        """Get current language display name"""
        return self.AVAILABLE_LANGUAGES.get(self.current_language, "Unknown")
    
    def get_available_languages(self):
        """Get dictionary of available languages"""
        return self.AVAILABLE_LANGUAGES.copy()


# Global localization instance (will be initialized by UI)
_loc_instance = None


def init_localization(language="en_US"):
    """Initialize global localization instance"""
    global _loc_instance
    _loc_instance = Localization(language)
    return _loc_instance


def get_localization():
    """Get global localization instance"""
    global _loc_instance
    if _loc_instance is None:
        _loc_instance = Localization()
    return _loc_instance


def t(key_path, **kwargs):
    """
    Shorthand function for translation
    
    Args:
        key_path: Dot-separated path to translation key
        **kwargs: Format arguments
    
    Returns:
        Translated string
    """
    return get_localization().get(key_path, **kwargs)
