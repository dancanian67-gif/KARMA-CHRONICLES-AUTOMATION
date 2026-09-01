"""Domain exceptions for episode storage."""


class EpisodeNotFoundError(Exception):
    """Raised when an episode directory or manifest cannot be found."""


class EpisodeAlreadyExistsError(Exception):
    """Raised when attempting to create an episode that already exists."""


class ManifestStorageError(Exception):
    """Raised when manifest persistence or validation fails."""
