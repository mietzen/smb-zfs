class SmbZfsError(Exception):
    """Base exception for all smb-zfs errors."""
    pass

class NotInitializedError(SmbZfsError):
    """Raised when the system has not been initialized by the setup command."""
    def __init__(self, message="System not set up. Run 'setup' first."):
        self.message = message
        super().__init__(self.message)

class AlreadyInitializedError(SmbZfsError):
    """Raised when trying to run setup on an already initialized system."""
    def __init__(self, message="System is already set up."):
        self.message = message
        super().__init__(self.message)

class ItemExistsError(SmbZfsError):
    """Raised when trying to create an item that already exists."""
    def __init__(self, item_type, name):
        self.message = f"{item_type.capitalize()} '{name}' already exists."
        super().__init__(self.message)

class ItemNotFoundError(SmbZfsError):
    """Raised when an item (user, group, share) cannot be found."""
    def __init__(self, item_type, name):
        self.message = f"{item_type.capitalize()} '{name}' not found or not managed by this tool."
        super().__init__(self.message)

class InvalidNameError(SmbZfsError):
    """Raised when an item name contains invalid characters."""
    def __init__(self, message="Name contains invalid characters."):
        self.message = message
        super().__init__(self.message)

class PrerequisiteError(SmbZfsError):
    """Raised when a required package or command is not found."""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class ImmutableError(SmbZfsError):
    """Raised when trying to modify or delete a protected item."""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
