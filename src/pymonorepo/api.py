"""The main entry module for the PyMonorepo build API."""
import typing as t
from collections.abc import MutableMapping
from pathlib import Path

from pymonorepo.wheel import WheelZip, write_wheel

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .pep621 import parse as parse_project


def read_pyproject_toml(path: Path) -> t.Dict[str, t.Any]:
    """Read the pyproject.toml file.

    :returns: The contents of the pyproject.toml file.
    """
    return tomllib.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


class Modules(MutableMapping[str, Path]):
    """A mapping of module name to path, does not allow overrides"""

    def __init__(self) -> None:
        self._data: t.Dict[str, Path] = {}

    def __getitem__(self, key: str) -> Path:
        return self._data[key]

    def __setitem__(self, key: str, value: Path) -> None:
        if key in self._data:
            raise KeyError(f"Duplicate module: {key!r}")
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> t.Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def build_wheel(
    root: Path,
    wheel_directory: Path,
    config_settings: t.Optional[t.Dict[str, t.Any]] = None,
    metadata_directory: t.Optional[str] = None,
    editable: bool = False,
) -> str:
    """Build a .whl file, and place it in the specified wheel_directory.

    :param root: The root of the project.
    :param wheel_directory: The directory in which to place the .whl file.
    :param config_settings: A dictionary of configuration settings.
    :param metadata_directory: The directory containing the .dist-info directory.
    :param editable: Whether to build an editable wheel.

    :returns: The basename (not the full path) of the .whl file it creates, as a unicode string.
    """
    # parse and validate the project configuration
    metadata = read_pyproject_toml(root.joinpath("pyproject.toml"))
    _result = parse_project(metadata, root)
    if _result.errors:
        raise RuntimeError(
            "Error(s) parsing pyproject.toml:\n%s"
            % "\n".join(f"[{e.key}]:{e.etype}: {e.msg}" for e in _result.errors)
        )
    project = _result.data
    if project.get("dynamic", []):
        # TODO allow for reading of dynamic version
        raise RuntimeError("pyproject.toml [project.dynamic] not supported")

    # add possible named module
    module_name = project["name"].replace("-", "_")
    modules = Modules()
    for rpath in [root, root / "src"]:
        for mpath in [rpath / module_name, rpath / (module_name + ".py")]:
            if mpath.exists():
                modules[module_name] = mpath

    # write the wheel
    wheel_path = wheel_directory.joinpath(
        f"{project['name']}-{project['version']}-py3-none-any.whl"
    )
    with WheelZip(wheel_path) as wheel:
        write_wheel(wheel, project, modules, editable=editable)

    return wheel_path.name


def build_sdist(
    root: Path,
    sdist_directory: Path,
    config_settings: t.Optional[t.Dict[str, t.Any]] = None,
) -> str:
    """Build a .tar.gz file, and place it in the specified sdist_directory.

    :param root: The root of the project.
    :param sdist_directory: The directory in which to place the .tar.gz file.
    :param config_settings: A dictionary of configuration settings.

    :returns: The basename (not the full path) of the .tar.gz file it creates, as a unicode string.
    """
    # TODO sdist
    raise NotImplementedError("sdist not yet implemented")
