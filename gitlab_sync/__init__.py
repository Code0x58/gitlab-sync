import logging
logger = logging.getLogger("gitlab-sync")


class ConfigurationError(ValueError):
    """Raised for errors during loading config."""
