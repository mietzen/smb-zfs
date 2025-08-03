import json
import os
import shutil
import logging
from typing import Any, Dict

from .errors import SmbZfsError

# --- Logger Setup ---
logger = logging.getLogger(__name__)


class StateManager:
    """Manages the application's state through a JSON file."""

    def __init__(self, state_path: str) -> None:
        """Initializes the state manager and loads the state file."""
        self.path: str = state_path
        self.data: Dict[str, Any] = {}
        logger.debug("StateManager initialized with path: %s", self.path)
        if not os.path.exists(self.path):
            logger.info("State file not found at %s. Initializing a new one.", self.path)
            self._initialize_state_file()
        self.load()

    def _initialize_state_file(self) -> None:
        """Initializes a new state file with a default structure."""
        logger.debug("Creating initial state structure in memory.")
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
            logger.debug("Ensuring directory exists: %s", os.path.dirname(self.path))
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            logger.info("Writing initial state to file: %s", self.path)
            with open(self.path, "w") as f:
                json.dump(initial_state, f, indent=2)
            os.chmod(self.path, 0o600)
            logger.debug("Set permissions for state file to 600.")
        except IOError as e:
            raise SmbZfsError(
                f"Failed to initialize state file at {self.path}: {e}"
            ) from e

    def load(self) -> None:
        """Loads the state data from the JSON file. Attempts recovery from backups on corruption."""
        logger.debug("Loading state from file: %s", self.path)
        try:
            with open(self.path, "r") as f:
                self.data = json.load(f)
            logger.info("State loaded successfully from %s.", self.path)
            return
        except (IOError, json.JSONDecodeError) as e:
            logger.warning("Failed to read or parse state file %s: %s", self.path, e)

        # Attempt recovery from backups
        backup_path = f"{self.path}.backup"
        init_backup_path = f"{self.path}.backup.init"

        # Try .backup first
        for candidate, label in [(backup_path, "backup"), (init_backup_path, "initial backup")]:
            if os.path.exists(candidate):
                try:
                    logger.warning("Attempting to restore state from %s file: %s", label, candidate)
                    shutil.copy(candidate, self.path)
                    with open(self.path, "r") as f:
                        self.data = json.load(f)
                    logger.info("State restored successfully from %s.", candidate)
                    return
                except Exception as e2:
                    logger.error("Failed to restore from %s (%s): %s", label, candidate, e2, exc_info=True)

        # If all recovery attempts failed, raise
        raise SmbZfsError(f"Failed to read or recover state file {self.path}.")

    def save(self) -> None:
        """Saves the current state data to the JSON file atomically with a backup."""
        logger.debug("Saving state to file: %s", self.path)
        tmp_path = f"{self.path}.tmp"
        backup_path = f"{self.path}.backup"
        try:
            # Create/refresh backup of current file if exists
            if os.path.exists(self.path):
                logger.debug("Creating backup of state file at %s.", backup_path)
                shutil.copy(self.path, backup_path)

            # Write atomically to a temporary file
            with open(tmp_path, "w") as f:
                json.dump(self.data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)

            # Atomic replace
            os.replace(tmp_path, self.path)
            logger.info("State saved successfully to %s.", self.path)
        except IOError as e:
            # Best-effort cleanup of tmp file
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise SmbZfsError(f"Failed to write state file {self.path}: {e}") from e

    def is_initialized(self) -> bool:
        """Checks if the system state is marked as initialized."""
        initialized = self.data.get("initialized", False)
        logger.debug("Checking initialization status: %s", initialized)
        return initialized

    def get(self, key: str, default: Any = None) -> Any:
        """Gets a top-level value from the state."""
        logger.debug("Getting state key '%s'.", key)
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Sets a top-level value in the state and saves."""
        logger.info("Setting state key '%s' to '%s'.", key, value)
        self.data[key] = value
        self.save()

    def get_item(self, category: str, name: str, default: Any = None) -> Any:
        """Gets a specific item from a category in the state."""
        logger.debug("Getting item '%s' from category '%s'.", name, category)
        return self.data.get(category, {}).get(name, default)

    def set_item(self, category: str, name: str, value: Any) -> None:
        """Sets a specific item in a category and saves the state."""
        logger.info("Setting item '%s' in category '%s'.", name, category)
        if category not in self.data:
            self.data[category] = {}
        self.data[category][name] = value
        self.save()

    def delete_item(self, category: str, name: str) -> None:
        """Deletes an item from a category and saves if it existed."""
        logger.info("Deleting item '%s' from category '%s'.", name, category)
        if self.data.get(category, {}).pop(name, None) is not None:
            logger.debug("Item found and removed. Saving state.")
            self.save()
        else:
            logger.debug("Item '%s' not found in category '%s'. No changes made.", name, category)

    def list_items(self, category: str) -> Dict[str, Any]:
        """Lists all items within a given category."""
        logger.debug("Listing all items from category '%s'.", category)
        return self.data.get(category, {})

    def get_data_copy(self) -> Dict[str, Any]:
        """Returns a deep copy of the current state data."""
        logger.debug("Creating a deep copy of the current state data.")
        return json.loads(json.dumps(self.data))
