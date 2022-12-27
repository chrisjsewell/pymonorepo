"""Wheel file writing.

See: https://peps.python.org/pep-0427/
"""
import hashlib
import os
import re
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
from .metadata import create_entrypoints, create_metadata
from .pep621 import ProjectData


def write_wheel(
    whl: "WheelWriter",
    root: Path,
    project_data: ProjectData,
    modules: t.Mapping[str, Path],
    editable: bool = False,
) -> None:
    """Write a wheel."""
    # write the python modules
    if not editable:
        for _, module in modules.items():
            if module.is_dir():
                copy_module_folder(whl, module)
            elif module.is_file():
                whl.write_path([module.name], module)
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
            whl.write_text([name], content)
        for dep in eproject.dependencies():
            req = Requirement(dep)
            if req not in project_data["dependencies"]:
                project_data["dependencies"].append(req)

    # write the dist_info (note this is recommended to be last in the file)
    wheel_metadata = whl.get_metadata(f"{__name__} {__version__}")
    whl.write_text((whl.dist_info, "WHEEL"), wheel_metadata)
    metadata_text = create_metadata(project_data, root)
    whl.write_text((whl.dist_info, "METADATA"), metadata_text)
    entrypoint_text = create_entrypoints(project_data)
    if entrypoint_text:
        whl.write_text((whl.dist_info, "entry_points.txt"), entrypoint_text)
    # write license files to dist_info
    # note, there is currently no standard for this, but it will likely be added in:
    # https://peps.python.org/pep-0639
    for license_file in project_data["licenses"]:
        if "path" in license_file:
            license_text = root.joinpath(license_file["path"]).read_text("utf-8")
            license_path = (whl.dist_info, "licenses") + license_file["path"].parts
            whl.write_text(license_path, license_text)


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


WheelWriterType = t.TypeVar("WheelWriterType", bound="WheelWriter")


class WheelWriter:
    """A wheel writer, implementing https://peps.python.org/pep-0427/.

    Should be used as a context manager.
    """

    def __init__(
        self,
        directory: Path,
        distribution: str,
        version: str,
        python: str,
        abi: str,
        platform: str,
        *,
        build: t.Optional[str] = None,
        purelib: bool = True,
    ) -> None:
        """Initialize.

        :param directory: The directory to write to.
        :param distribution: The distribution name.
        :param version: The distribution version.
        :param build: The build number.
        :param python: The python version.
        :param abi: The ABI tag.
        :param platform: The platform tag.
        """
        self._info = {
            "distribution": distribution,
            "version": version,
            "python": python,
            "abi": abi,
            "platform": platform,
        }
        if build is not None:
            self._info["build"] = build
        for key, value in self._info.items():
            self._info[key] = re.sub("[^\w\d.]+", "_", value, re.UNICODE)
        name = "-".join(
            self._info[key]
            for key in ("distribution", "version", "build", "python", "abi", "platform")
            if key in self._info
        )
        self._purelib = purelib
        self._path = directory.joinpath(f"{name}.whl")
        self._zip: t.Optional[zipfile.ZipFile] = None
        self._records: t.List[Record] = []
        # fixed timestamp for reproducible builds
        # TODO get the timestamp from the SOURCE_DATE_EPOCH environment variable
        self._time_stamp = (2016, 1, 1, 0, 0, 0)

    @staticmethod
    def raise_not_open() -> t.NoReturn:
        """Assert that the zip file is open."""
        raise IOError("Wheel file is not open.")

    def __enter__(self: WheelWriterType) -> WheelWriterType:
        """Enter the context manager."""
        self._zip = zipfile.ZipFile(self._path, "w", compression=zipfile.ZIP_DEFLATED)
        return self

    def __exit__(
        self,
        exc_type: t.Optional[t.Type[BaseException]],
        exc_val: t.Optional[BaseException],
        exc_tb: t.Optional[TracebackType],
    ) -> None:
        """Exit the context manager."""
        if self._zip is None:
            self.raise_not_open()

        # write the RECORD file
        if not exc_type:
            record_text = ""
            for record in self.records:
                record_text += f"{record.path},{record.hash},{record.size}\n"
            # no hash or size for the RECORD file itself
            record_text += f"{self.dist_info}/RECORD,,\n"
            self.write_text((self.dist_info, "RECORD"), record_text)
            self._records.pop()

        self._zip.close()
        self._zip = None

    @property
    def name(self) -> str:
        """Return the basename."""
        return self._path.name

    @property
    def dist_info(self) -> str:
        """Return dist-info directory name."""
        return f'{self._info["distribution"]}-{self._info["version"]}.dist-info'

    @property
    def tags(self) -> t.List[str]:
        """Return the expanded compatibility tags."""
        # TODO support multiple tags
        return [f"{self._info['python']}-{self._info['abi']}-{self._info['platform']}"]

    @property
    def purelib(self) -> bool:
        """Return whether the wheel is purelib."""
        return self._purelib

    @property
    def records(self) -> t.List[Record]:
        """Return the records of written files."""
        return self._records

    def get_metadata(self, generator: str) -> str:
        """Return the metadata, to place in the METADATA file.

        :param generator: The generator name.
        """
        wheel_text = dedent(
            f"""\
        Wheel-Version: 1.0
        Generator: {generator}
        Root-Is-Purelib: {'true' if self.purelib else 'false'}
        """
        )
        for tag in self.tags:
            wheel_text += f"Tag: {tag}"
        if self._info.get("build"):
            wheel_text += f"Build: {self._info['build']}"
        return wheel_text + "\n"

    # methods that require an open zip file

    def list_files(self) -> t.List[str]:
        """Return a list of files in the wheel."""
        if self._zip is None:
            self.raise_not_open()
        return self._zip.namelist()

    def write_text(
        self,
        path: t.Sequence[str],
        text: str,
        encoding: str = "utf-8",
    ) -> Record:
        """Write text to the wheel.

        :param path: The path to write to in the wheel.
        :param text: The text to write.
        :param encoding: The encoding to use.

        :returns: The byte length and hash of the content.
        """
        if self._zip is None:
            self.raise_not_open()
        content = text.encode(encoding)
        hashsum = hashlib.sha256(content)
        zinfo = zipfile.ZipInfo("/".join(path), self._time_stamp)
        zinfo.external_attr = 0o644 << 16
        self._zip.writestr(zinfo, content, compress_type=zipfile.ZIP_DEFLATED)
        self._records.append(Record("/".join(path), encode_hash(hashsum), len(content)))
        return self._records[-1]

    def write_path(
        self,
        path: t.Sequence[str],
        source: Path,
    ) -> Record:
        """Write an external path to the wheel.

        :param path: The path to write to in the wheel.
        :param source: The path to write from.

        :returns: The byte length and hash of the content.
        """
        if self._zip is None:
            self.raise_not_open()
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

        self._records.append(
            Record("/".join(path), encode_hash(hashsum), source.stat().st_size)
        )
        return self._records[-1]


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


def encode_hash(hashsum: t.Any) -> str:
    """Encode a hash."""
    hash_digest = urlsafe_b64encode(hashsum.digest()).decode("ascii").rstrip("=")
    return f"{hashsum.name}={hash_digest}"


def copy_module_folder(
    whl: WheelWriter,
    source: Path,
    exclude: t.Sequence[str] = ("__pycache__", "*.pyc"),
) -> t.List[Record]:
    """Copy a folder to the wheel.

    :source: The path to the folder to copy.
    :exclude: A list of fnmatch patterns to exclude file/directory names.
    """
    records: t.List[Record] = []

    for file_path in iter_files(source, exclude):
        rel_path = file_path.relative_to(source.parent).parts
        record = whl.write_path(rel_path, file_path)
        records.append(record)

    return records


def iter_files(source: Path, exclude: t.Sequence[str]) -> t.Iterable[Path]:
    """Copy a folder to the wheel.

    :source: The path to the folder to copy.
    :exclude: A list of fnmatch patterns to exclude file/directory names.
    """

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
