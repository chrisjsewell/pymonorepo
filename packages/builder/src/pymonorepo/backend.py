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
import typing as t
from pathlib import Path

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
    metadir = Path(metadata_directory) if metadata_directory else None
    return build.build_wheel(CWD, Path(wheel_directory), metadir).path.name


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
    metadir = Path(metadata_directory) if metadata_directory else None
    return build.build_wheel(
        CWD, Path(wheel_directory), metadir, editable=True
    ).path.name


def prepare_metadata_for_build_wheel(
    metadata_directory: str, config_settings: t.Optional[t.Dict[str, t.Any]] = None
) -> str:
    """Prepare the metadata for a wheel build.

    :param metadata_directory: The directory in which to place the .dist-info directory.
    :param config_settings: A dictionary of configuration settings.

    :returns: The basename (not the full path) of the .dist-info directory it creates.
    """
    return build.build_wheel_metadata(CWD, Path(metadata_directory)).metadata.dist_info


prepare_metadata_for_build_editable = prepare_metadata_for_build_wheel
