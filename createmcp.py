import json
import os

# Define the path to the settings file relative to the project root
SETTINGS_DIR = ".gemini"
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")


def read_settings() -> dict:
    """
    Reads the settings from the .gemini/settings.json file.

    Returns:
        A dictionary of settings, or an empty dictionary if the file
        doesn't exist or is invalid.
    """
    if not os.path.exists(SETTINGS_FILE):
        print(f"Settings file not found at '{SETTINGS_FILE}'. Returning empty settings.")
        return {}

    try:
        with open(SETTINGS_FILE, 'r') as f:
            # Handle empty file case
            content = f.read()
            if not content:
                print(f"Settings file '{SETTINGS_FILE}' is empty. Returning empty settings.")
                return {}
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {SETTINGS_FILE}: {e}")
        return {}
    except IOError as e:
        print(f"Error reading from file {SETTINGS_FILE}: {e}")
        return {}


# --- Main execution block ---
if __name__ == "__main__":
    print(f"Attempting to read settings from '{SETTINGS_FILE}'...")
    settings_data = read_settings()

    if settings_data:
        print("\n--- Successfully read settings ---")
        # Pretty-print the settings using json.dumps for clear formatting
        print(json.dumps(settings_data, indent=4))
        
        # Example of how to access a specific setting
        api_key = settings_data.get("api_key")
        if api_key:
            print(f"\nAPI Key found: {api_key}")
        else:
            print("\nAPI Key not found in settings.")
            
    else:
        print("\nCould not read settings. The file might be missing, empty, or contain invalid JSON.")