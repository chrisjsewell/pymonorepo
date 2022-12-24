"""Wheel file writing.

See: https://peps.python.org/pep-0427/
"""
import hashlib
import os
import typing as t
import zipfile
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from textwrap import dedent
from types import TracebackType

import editables
from packaging.requirements import Requirement

from . import __name__, __version__
from .metadata import create_metadata
from .pep621 import ProjectData


def write_wheel(
    whl: "WheelInterface",
    project_data: ProjectData,
    modules: t.Mapping[str, Path],
    editable: bool = False,
) -> None:
    """Write a wheel."""
    records: t.List[Record] = []

    # write the python modules
    if not editable:
        for _, module in modules.items():
            if module.is_dir():
                records.extend(copy_folder(whl, module))
            elif module.is_file():
                records.append(whl.write_path([module.name], module))
            else:
                raise FileNotFoundError(module)
    else:
        eproject = editables.EditableProject(project_data["name"], ".")
        for module_name, module in modules.items():
            if module.is_dir() or module.is_file():
                eproject.map(module_name, module.absolute())
            else:
                raise FileNotFoundError(module)
        for name, content in eproject.files():
            records.append(whl.write_text([name], content))
        for dep in eproject.dependencies():
            req = Requirement(dep)
            if req not in project_data["dependencies"]:
                project_data["dependencies"].append(req)

    # write the metadata
    dist_info = f'{project_data["name"]}-{project_data["version"]}.dist-info'
    records.append(write_spec(whl, dist_info, f"{__name__} {__version__}"))
    metadata_text = create_metadata(project_data)
    records.append(whl.write_text((dist_info, "METADATA"), metadata_text))
    ep_record = write_entrypoints(whl, dist_info, project_data)
    if ep_record:
        records.append(ep_record)
    # TODO write license file(s) to dist_info

    # write the file record CSV
    write_records(whl, dist_info, records)


class WheelInterface(t.Protocol):
    """An interface to a wheel object."""

    def __enter__(self) -> "WheelInterface":
        """Enter the context manager."""

    def __exit__(
        self,
        exc_type: t.Optional[t.Type[BaseException]],
        exc_val: t.Optional[BaseException],
        exc_tb: t.Optional[TracebackType],
    ) -> None:
        """Exit the context manager."""

    @property
    def name(self) -> str:
        """Return the basename."""

    def write_text(
        self,
        path: t.Sequence[str],
        text: str,
        encoding: str = "utf-8",
    ) -> "Record":
        """Write text to the wheel.

        :param path: The path to write to in the wheel.
        :param text: The text to write.
        :param encoding: The encoding to use.

        :returns: The byte length and hash of the content.
        """

    def write_path(
        self,
        path: t.Sequence[str],
        source: Path,
    ) -> "Record":
        """Write an external path to the wheel.

        :param path: The path to write to in the wheel.
        :param source: The path to write from.

        :returns: The byte length and hash of the content.
        """


def encode_hash(hashsum: t.Any) -> str:
    hash_digest = urlsafe_b64encode(hashsum.digest()).decode("ascii").rstrip("=")
    return f"{hashsum.name}={hash_digest}"


class WheelPath(WheelInterface):
    """A folder as a wheel."""

    def __init__(self, path: Path) -> None:
        """Initialize."""
        self._path = path

    def __enter__(self) -> "WheelPath":
        """Enter the context manager."""
        self._path.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(
        self,
        exc_type: t.Optional[t.Type[BaseException]],
        exc_val: t.Optional[BaseException],
        exc_tb: t.Optional[TracebackType],
    ) -> None:
        """Exit the context manager."""

    @property
    def name(self) -> str:
        return self._path.name

    def write_text(
        self,
        path: t.Sequence[str],
        text: str,
        encoding: str = "utf-8",
    ) -> "Record":
        subpath = self._path.joinpath(*path)
        subpath.parent.mkdir(parents=True, exist_ok=True)
        subpath.write_text(text, encoding=encoding)

        content = text.encode(encoding)
        hashsum = hashlib.sha256(content)
        return Record("/".join(path), encode_hash(hashsum), len(content))

    def write_path(
        self,
        path: t.Sequence[str],
        source: Path,
    ) -> "Record":
        subpath = self._path.joinpath(*path)
        subpath.parent.mkdir(parents=True, exist_ok=True)
        # stream the file content whilst computing the hash
        # to avoid loading the whole file into memory
        hashsum = hashlib.sha256()
        with source.open("rb") as src, subpath.open("wb") as dest:
            while True:
                buf = src.read(1024 * 8)
                if not buf:
                    break
                hashsum.update(buf)
                dest.write(buf)
        # copy permissions
        subpath.chmod(source.stat().st_mode)

        return Record("/".join(path), encode_hash(hashsum), source.stat().st_size)


class WheelZip(WheelInterface):
    """A zip file as a wheel."""

    def __init__(self, path: Path) -> None:
        """Initialize."""
        self._path = path
        self._zip = zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED)
        # fixed timestamp for reproducible builds
        # TODO get the timestamp from the SOURCE_DATE_EPOCH environment variable
        self._time_stamp = (2016, 1, 1, 0, 0, 0)

    def __enter__(self) -> "WheelZip":
        return self

    def __exit__(
        self,
        exc_type: t.Optional[t.Type[BaseException]],
        exc_val: t.Optional[BaseException],
        exc_tb: t.Optional[TracebackType],
    ) -> None:
        self._zip.close()

    @property
    def name(self) -> str:
        return self._path.name

    def write_text(
        self,
        path: t.Sequence[str],
        text: str,
        encoding: str = "utf-8",
    ) -> "Record":
        content = text.encode(encoding)
        hashsum = hashlib.sha256(content)
        zinfo = zipfile.ZipInfo("/".join(path), self._time_stamp)
        zinfo.external_attr = 0o644 << 16
        self._zip.writestr(zinfo, content, compress_type=zipfile.ZIP_DEFLATED)
        return Record("/".join(path), encode_hash(hashsum), len(content))

    def write_path(
        self,
        path: t.Sequence[str],
        source: Path,
    ) -> "Record":
        zinfo = zipfile.ZipInfo("/".join(path), self._time_stamp)
        # Normalize permission bits to either 755 (executable) or 644
        st_mode = source.stat().st_mode
        new_mode = normalize_file_permissions(st_mode)
        zinfo.external_attr = (new_mode & 0xFFFF) << 16
        # stream the file content whilst computing the hash
        # to avoid loading the whole file into memory
        hashsum = hashlib.sha256()
        with source.open("rb") as src, self._zip.open(zinfo, "w") as dest:
            while True:
                buf = src.read(1024 * 8)
                if not buf:
                    break
                hashsum.update(buf)
                dest.write(buf)

        return Record("/".join(path), encode_hash(hashsum), source.stat().st_size)


def normalize_file_permissions(st_mode: int) -> int:
    """Normalize the permission bits in the st_mode field from stat to 644/755

    Popular VCSs only track whether a file is executable or not. The exact
    permissions can vary on systems with different umasks. Normalising
    to 644 (non executable) or 755 (executable) makes builds more reproducible.
    """
    # Set 644 permissions, leaving higher bits of st_mode unchanged
    new_mode = (st_mode | 0o644) & ~0o133
    if st_mode & 0o100:
        new_mode |= 0o111  # Executable: 644 -> 755
    return new_mode


@dataclass
class Record:
    """A RECORD file entry.

    See:
    https://packaging.python.org/en/latest/specifications/recording-installed-packages/#the-record-file
    """

    path: str
    """Absolute, or relative to the directory containing the .dist-info directory."""
    hash: str
    """The name of a hash algorithm from hashlib.algorithms_guaranteed,
    followed by the equals character = and the digest of the file’s contents,
    encoded with the urlsafe-base64-nopad encoding.
    """
    size: int
    """File size in bytes, as a base 10 integer."""


def write_spec(whl: WheelInterface, dist_info: str, generator: str) -> Record:
    """Write the `WHEEL` file.

    :dist_info: The name of the .dist-info directory.
    :generator: The name of the wheel generator.
    """
    wheel_text = dedent(
        f"""\
        Wheel-Version: 1.0
        Generator: {generator}
        Root-Is-Purelib: true
        Tag: py3-none-any
        """
    )
    return whl.write_text((dist_info, "WHEEL"), wheel_text)


def write_entrypoints(
    whl: WheelInterface, dist_info: str, project: ProjectData
) -> t.Optional[Record]:
    """Write the `entry_points.txt` file.

    :dist_info: The name of the .dist-info directory.
    :project: The project data.
    """
    if project.get("entry_points"):
        entrypoint_text = ""
        for group_name in sorted(project["entry_points"]):
            entrypoint_text += f"[{group_name}]\n"
            group = project["entry_points"][group_name]
            for name in sorted(group):
                val = group[name]
                entrypoint_text += f"{name}={val}\n"
            entrypoint_text += "\n"
        return whl.write_text((dist_info, "entry_points.txt"), entrypoint_text)
    return None


def copy_folder(
    whl: WheelInterface,
    source: Path,
    exclude: t.Sequence[str] = ("__pycache__", "*.pyc"),
) -> t.List[Record]:
    """Copy a folder to the wheel.

    :source: The path to the folder to copy.
    :exclude: A list of fnmatch patterns to exclude.
    """
    records: t.List[Record] = []

    for file_path in iter_files(source, exclude):
        rel_path = file_path.relative_to(source.parent).parts
        record = whl.write_path(rel_path, file_path)
        records.append(record)

    return records


def iter_files(
    source: Path, exclude: t.Sequence[str] = ("__pycache__", "*.pyc")
) -> t.Iterable[Path]:
    """Copy a folder to the wheel."""

    def _include(_path: str) -> bool:
        _name = os.path.basename(_path)
        return not any(fnmatch(_name, ex) for ex in exclude)

    # Ensure we sort all files and directories so the order is stable
    for dirpath, dirs, files in os.walk(source):
        for file in sorted(files):
            full_path = os.path.join(dirpath, file)
            if _include(full_path):
                yield Path(full_path)

        dirs[:] = [d for d in sorted(dirs) if _include(d)]


def write_records(whl: WheelInterface, dist_info: str, records: t.List[Record]) -> None:
    """Write the `RECORD` file.

    :dist_info: The name of the .dist-info directory.
    :records: A list of records.
    """
    record_text = ""

    for record in records:
        record_text += f"{record.path},{record.hash},{record.size}\n"

    record_text += f"{dist_info}/RECORD,,\n"

    whl.write_text((dist_info, "RECORD"), record_text)
