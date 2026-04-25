from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("spec4")
except PackageNotFoundError:
    __version__ = "unknown"
