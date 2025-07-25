import json
import os
import shutil

from .errors import SmbZfsError


class StateManager:
    def __init__(self, state_path):
        self.path = state_path
        self.data = {}
        if not os.path.exists(self.path):
            self._initialize_state_file()
        self.load()

    def _initialize_state_file(self):
        """Initializes the state file with the new structure."""
        initial_state = {
            "initialized": False,
            "primary_pool": None,
            "secondary_pools": [],
            "server_name": None,
            "workgroup": None,
            "macos_optimized": False,
            "default_home_quota": None,
            "users": {},
            "shares": {},
            "groups": {},
        }
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(initial_state, f, indent=2)
            os.chmod(self.path, 0o600)
        except IOError as e:
            raise SmbZfsError(
                f"Failed to initialize state file at {self.path}: {e}"
            ) from e

    def load(self):
        try:
            with open(self.path, "r") as f:
                self.data = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            raise SmbZfsError(
                f"Failed to read or parse state file {self.path}: {e}"
            ) from e

    def save(self):
        try:
            backup_path = f"{self.path}.backup"
            if os.path.exists(self.path):
                shutil.copy(self.path, backup_path)

            with open(self.path, "w") as f:
                json.dump(self.data, f, indent=2)
            os.chmod(self.path, 0o600)
        except IOError as e:
            raise SmbZfsError(
                f"Failed to write state file {self.path}: {e}") from e

    def is_initialized(self):
        return self.data.get("initialized", False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def get_item(self, category, name, default=None):
        return self.data.get(category, {}).get(name, default)

    def set_item(self, category, name, value):
        if category not in self.data:
            self.data[category] = {}
        self.data[category][name] = value
        self.save()

    def delete_item(self, category, name):
        if self.data.get(category, {}).pop(name, None):
            self.save()

    def list_items(self, category):
        return self.data.get(category, {})
