"""
Version Selector
Manages user preference for console or UI mode
"""

import os
import json


class VersionSelector:
    """Handles version preference storage and selection"""
    
    def __init__(self):
        self.config_file = "version_config.json"
        self.config = self.load_config()
    
    def load_config(self):
        """Load version configuration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_config(self):
        """Save version configuration"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Failed to save version config: {e}")
    
    def has_preference(self):
        """Check if user has already set a preference"""
        return "preferred_version" in self.config
    
    def get_preference(self):
        """Get stored preference"""
        return self.config.get("preferred_version", None)
    
    def set_preference(self, version):
        """Set version preference (console or ui)"""
        self.config["preferred_version"] = version
        self.save_config()
    
    def prompt_version_choice(self):
        """Prompt user to choose between console and UI version"""
        print("\n" + "="*50)
        print("🎨 ROBLOX ACCOUNT MANAGER - VERSION SELECTOR")
        print("="*50)
        print("\nChoose your preferred interface:")
        print("1. Console Mode (Text-based interface)")
        print("2. UI Mode (Graphical interface)")
        print("-" * 50)
        
        while True:
            choice = input("\nSelect version (1 or 2): ").strip()
            
            if choice == '1':
                self.set_preference("console")
                print("\n✓ Console mode selected!")
                print("  You can change this later by deleting 'version_config.json'\n")
                return "console"
            elif choice == '2':
                self.set_preference("ui")
                print("\n✓ UI mode selected!")
                print("  You can change this later by deleting 'version_config.json'\n")
                return "ui"
            else:
                print("❌ Invalid choice. Please enter 1 or 2.")

        print()
        input("Press Enter to exit...")
        sys.exit(1)
