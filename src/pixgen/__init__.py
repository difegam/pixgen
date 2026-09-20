import importlib.metadata

from pixgen.cli.app import app

def get_version():
    try:
        return importlib.metadata.version("pixgen")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"

__version__ = get_version()



def main() -> None:
    app()
