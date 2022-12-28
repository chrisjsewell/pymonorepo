"""The main entry module for the PyMonorepo build API."""
import typing as t
from pathlib import Path

from .analyse import analyse_project
from .wheel import WheelWriter, write_wheel


def build_wheel(
    root: Path,
    wheel_directory: Path,
    *,
    editable: bool = False,
    meta_only: bool = False,
) -> WheelWriter:
    """Build a .whl file, and place it in the specified wheel_directory.

    :param root: The root of the project.
    :param wheel_directory: The directory in which to place the .whl file.
    :param editable: Whether to build an editable wheel.
    :param meta_only: Whether to build a metadata-only wheel.

    :returns: The basename (not the full path) of the .whl file it creates, as a unicode string.
    """
    proj_config, modules = analyse_project(root)

    with WheelWriter(
        wheel_directory,
        proj_config["name"],
        str(proj_config["version"]),
        "py3",
        "none",
        "any",
    ) as wheel:
        write_wheel(
            wheel, root, proj_config, modules, editable=editable, meta_only=meta_only
        )
    return wheel


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
