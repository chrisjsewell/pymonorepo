"""A module to implement the build backend interface,
defined in https://peps.python.org/pep-0517,
and https://peps.python.org/pep-0660.

Mandatory hooks:

- build_wheel
- build_sdist

Optional hooks:

- build_editable
- prepare_metadata_for_build_wheel
- prepare_metadata_for_build_editable
"""
import shutil
import typing as t
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from . import build

CWD = Path.cwd()
"""This module should always be called with the CWD set to the root of the project."""


def build_wheel(
    wheel_directory: str,
    config_settings: t.Optional[t.Dict[str, t.Any]] = None,
    metadata_directory: t.Optional[str] = None,
) -> str:
    """Must build a .whl file, and place it in the specified wheel_directory.

    :param wheel_directory: The directory in which to place the .whl file.
    :param config_settings: A dictionary of configuration settings.
    :param metadata_directory: The directory containing the .dist-info directory.

    :returns: The basename (not the full path) of the .whl file it creates, as a unicode string.
    """
    return build.build_wheel(CWD, Path(wheel_directory)).path.name


def build_sdist(
    sdist_directory: str,
    config_settings: t.Optional[t.Dict[str, t.Any]] = None,
) -> str:
    """Must build a .tar.gz file, and place it in the specified sdist_directory.

    :param sdist_directory: The directory in which to place the .tar.gz file.
    :param config_settings: A dictionary of configuration settings.

    :returns: The basename (not the full path) of the .tar.gz file it creates, as a unicode string.
    """
    return build.build_sdist(CWD, Path(sdist_directory), config_settings).path.name


def build_editable(
    wheel_directory: str,
    config_settings: t.Optional[t.Dict[str, t.Any]] = None,
    metadata_directory: t.Optional[str] = None,
) -> str:
    """Must build a .whl file, and place it in the specified wheel_directory.

    :param wheel_directory: The directory in which to place the .whl file.
    :param config_settings: A dictionary of configuration settings.
    :param metadata_directory: The directory containing the .dist-info directory.

    :returns: The basename (not the full path) of the .whl file it creates.
        The filename for the “editable” wheel needs to be PEP 427 compliant too.
    """
    return build.build_wheel(CWD, Path(wheel_directory), editable=True).path.name


def prepare_metadata_for_build_wheel(
    metadata_directory: str, config_settings: t.Optional[t.Dict[str, t.Any]] = None
) -> str:
    """Prepare the metadata for a wheel build.

    :param metadata_directory: The directory in which to place the metadata.
    :param config_settings: A dictionary of configuration settings.
    """
    with TemporaryDirectory() as path_str:
        path = Path(path_str)
        wheel = build.build_wheel(CWD, path, meta_only=True)
        # unpack the wheel to temporary directory
        with zipfile.ZipFile(wheel.path, mode="r") as zip_file:
            zip_file.extractall(path)
        # move the dist-info directory to the metadata directory
        shutil.move(str(path / wheel.dist_info), metadata_directory)
    return wheel.dist_info


prepare_metadata_for_build_editable = prepare_metadata_for_build_wheel
