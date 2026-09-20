from platformdirs import PlatformDirs

dirs = PlatformDirs(
    appname="pixgen",
)

CONFIG_FILE_NAME = "config.toml"


def resolve_config_path() -> str:
    return str(dirs.user_config_path / CONFIG_FILE_NAME)


def cache_path() -> str:
    """Return the path to the user cache directory."""
    return str(dirs.user_cache_path)


def data_path() -> str:
    """Return the path to the user data directory."""
    return str(dirs.user_data_path)
