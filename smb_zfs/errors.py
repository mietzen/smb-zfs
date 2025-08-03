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


class StateItemNotFoundError(SmbZfsError):
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

class InvalidInputError(SmbZfsError):
    """Raised when provided input fails validation or has an invalid format/value."""
 
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
 
class MissingInput(SmbZfsError):
    """Raised when a required input parameter is missing for the requested operation."""
 
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ZfsCmdError(SmbZfsError):
    """Raised when trying to execute zfs commands."""

    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
