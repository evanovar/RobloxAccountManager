"""
Theme Manager for Roblox Account Manager
Handles loading, applying, importing, and exporting themes
"""

import json
import os
from pathlib import Path


class ThemeManager:
    """Manages themes and applies them to the UI"""

    BUILTIN_THEMES = {
        "dark": {
            "metadata": {
                "name": "Dark",
                "author": "evanovar",
                "description": "Default dark theme with clean contrast",
            },
            "colors": {
                "bg_dark": "#2b2b2b",
                "bg_mid": "#3a3a3a",
                "bg_light": "#4b4b4b",
                "fg_text": "#ffffff",
                "fg_accent": "#0078D7",
            },
            "fonts": {
                "family": "Segoe UI",
                "size_base": 10,
            },
        },
        "light": {
            "metadata": {
                "name": "Light",
                "author": "evanovar",
                "description": "Bright light theme with subtle contrast",
            },
            "colors": {
                "bg_dark": "#f5f5f5",
                "bg_mid": "#ffffff",
                "bg_light": "#e8e8e8",
                "fg_text": "#222222",
                "fg_accent": "#0078D7",
            },
            "fonts": {
                "family": "Segoe UI",
                "size_base": 10,
            },
        },
        "dracula": {
            "metadata": {
                "name": "Dracula",
                "author": "evanovar",
                "description": "Classic Dracula-inspired cool dark palette",
            },
            "colors": {
                "bg_dark": "#282a36",
                "bg_mid": "#303341",
                "bg_light": "#44475a",
                "fg_text": "#f8f8f2",
                "fg_accent": "#8be9fd",
            },
            "fonts": {
                "family": "Segoe UI",
                "size_base": 10,
            },
        },
    }
    
    DEFAULT_THEME = {
        "metadata": {
            "name": "Dark",
            "author": "evanovar",
            "description": "Default dark theme"
        },
        "colors": {
            "bg_dark": "#2b2b2b",
            "bg_mid": "#3a3a3a",
            "bg_light": "#4b4b4b",
            "fg_text": "white",
            "fg_accent": "#0078D7"
        },
        "fonts": {
            "family": "Segoe UI",
            "size_base": 10
        }
    }
    
    def __init__(self, themes_dir="AccountManagerData/themes"):
        """Initialize theme manager with themes directory"""
        self.themes_dir = themes_dir
        self.builtin_themes_dir = os.path.join(themes_dir, "builtin")
        self.custom_themes_dir = os.path.join(themes_dir, "custom")
        self.seed_marker_path = os.path.join(themes_dir, ".builtin_seeded")
        self.current_theme = None
        
        self._ensure_directories()
        self._seed_builtin_themes_once()
        
    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        Path(self.themes_dir).mkdir(parents=True, exist_ok=True)
        Path(self.builtin_themes_dir).mkdir(parents=True, exist_ok=True)
        Path(self.custom_themes_dir).mkdir(parents=True, exist_ok=True)

    def _seed_builtin_themes_once(self):
        """Seed builtin themes only once per install.

        If themes already exist from an older version but marker is missing,
        we write the marker without reseeding to avoid overwriting/deleting behavior.
        """
        if os.path.exists(self.seed_marker_path):
            return

        existing_builtin_json = []
        if os.path.exists(self.builtin_themes_dir):
            existing_builtin_json = [
                name for name in os.listdir(self.builtin_themes_dir)
                if name.lower().endswith(".json")
            ]

        if existing_builtin_json:
            Path(self.seed_marker_path).write_text("seeded\n", encoding="utf-8")
            return

        for theme_key, theme_data in self.BUILTIN_THEMES.items():
            out_path = os.path.join(self.builtin_themes_dir, f"{theme_key}.json")
            merged = self._merge_with_defaults(theme_data)
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(merged, handle, indent=2)

        Path(self.seed_marker_path).write_text("seeded\n", encoding="utf-8")
        
    def get_available_themes(self):
        """Get list of all available themes (builtin + custom)"""
        themes = {}
        
        if os.path.exists(self.builtin_themes_dir):
            for filename in os.listdir(self.builtin_themes_dir):
                if filename.endswith(".json"):
                    theme_name = filename[:-5]
                    themes[theme_name] = {"path": os.path.join(self.builtin_themes_dir, filename), "builtin": True}
        
        if os.path.exists(self.custom_themes_dir):
            for filename in os.listdir(self.custom_themes_dir):
                if filename.endswith(".json"):
                    theme_name = filename[:-5]
                    themes[theme_name] = {"path": os.path.join(self.custom_themes_dir, filename), "builtin": False}
        
        return themes
    
    def load_theme(self, theme_name):
        """Load a theme by name and return the theme data"""
        themes = self.get_available_themes()
        
        if theme_name not in themes:
            theme_name_lower = theme_name.lower()
            for available_name in themes.keys():
                if available_name.lower() == theme_name_lower:
                    theme_name = available_name
                    break
        
        if theme_name not in themes:
            print(f"[WARNING] Theme '{theme_name}' not found, using default")
            return self.DEFAULT_THEME
        
        try:
            theme_path = themes[theme_name]["path"]
            with open(theme_path, 'r', encoding='utf-8') as f:
                theme_data = json.load(f)
            
            merged_theme = self._merge_with_defaults(theme_data)
            self.current_theme = theme_name
            return merged_theme
        except Exception as e:
            print(f"[ERROR] Failed to load theme '{theme_name}': {e}")
            return self.DEFAULT_THEME
    
    def _merge_with_defaults(self, user_theme):
        """Merge user theme with defaults to ensure all keys exist"""
        merged = json.loads(json.dumps(self.DEFAULT_THEME))
        
        if "metadata" in user_theme:
            merged["metadata"].update(user_theme["metadata"])
        
        if "colors" in user_theme:
            merged["colors"].update(user_theme["colors"])
        
        if "fonts" in user_theme:
            merged["fonts"].update(user_theme["fonts"])
        
        return merged
    
    def save_theme(self, theme_name, theme_data, is_custom=True):
        """Save a theme to file"""
        try:
            theme_dir = self.custom_themes_dir if is_custom else self.builtin_themes_dir
            theme_path = os.path.join(theme_dir, f"{theme_name}.json")
            
            with open(theme_path, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=2)
            
            print(f"[INFO] Theme '{theme_name}' saved successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save theme '{theme_name}': {e}")
            return False
    
    def import_theme(self, file_path):
        """Import a theme from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                theme_data = json.load(f)
            
            if "metadata" not in theme_data or "name" not in theme_data["metadata"]:
                raise ValueError("Invalid theme: missing metadata.name")
            
            theme_name = theme_data["metadata"]["name"]
            
            return self.save_theme(theme_name, theme_data, is_custom=True)
        except Exception as e:
            print(f"[ERROR] Failed to import theme from '{file_path}': {e}")
            return False
    
    def export_theme(self, theme_name, export_path):
        """Export a theme to a file"""
        try:
            theme_data = self.load_theme(theme_name)
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=2)
            
            print(f"[INFO] Theme '{theme_name}' exported to '{export_path}'")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to export theme '{theme_name}': {e}")
            return False
    
    def delete_theme(self, theme_name):
        """Delete any theme file (custom or builtin)."""
        themes = self.get_available_themes()
        
        if theme_name not in themes:
            print(f"[ERROR] Theme '{theme_name}' not found")
            return False
        
        try:
            theme_path = themes[theme_name]["path"]
            os.remove(theme_path)
            print(f"[INFO] Theme '{theme_name}' deleted")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to delete theme '{theme_name}': {e}")
            return False
    
    def duplicate_theme(self, source_name, new_name):
        """Duplicate a theme"""
        try:
            theme_data = self.load_theme(source_name)
            theme_data["metadata"]["name"] = new_name
            return self.save_theme(new_name, theme_data, is_custom=True)
        except Exception as e:
            print(f"[ERROR] Failed to duplicate theme '{source_name}': {e}")
            return False
    
    def get_theme_colors(self, theme_name):
        """Get colors from a theme"""
        theme_data = self.load_theme(theme_name)
        return theme_data.get("colors", {})
    
    def get_theme_fonts(self, theme_name):
        """Get fonts from a theme"""
        theme_data = self.load_theme(theme_name)
        return theme_data.get("fonts", {})
    
    def get_theme_background(self, theme_name):
        """Get background settings from a theme"""
        theme_data = self.load_theme(theme_name)
        return theme_data.get("background", {})
