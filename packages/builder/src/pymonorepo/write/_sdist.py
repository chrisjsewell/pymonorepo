"""Sdist file writing.

See: https://peps.python.org/pep-0517/#source-distributions
"""
import io
import os
import tarfile
import typing as t
from gzip import GzipFile
from pathlib import Path
from types import TracebackType

from ..analyse import ProjectAnalysis
from ._files import gather_files, normalize_file_permissions
from ._metadata import create_metadata


def write_sdist(sdist: "SdistWriter", project: ProjectAnalysis) -> None:
    """Write an sdist."""
    # TODO config options to turn off git tracked files, include and exclude
    for file_path in gather_files(project.root):
        rel_path = file_path.relative_to(project.root).parts
        sdist.write_path(rel_path, file_path)
    metadata_text = create_metadata(project.project, project.root)
    sdist.write_text(("PKG-INFO",), metadata_text)


SdistWriterType = t.TypeVar("SdistWriterType", bound="SdistWriter")


class SdistWriter:
    """Write a sdist file, implementing https://peps.python.org/pep-0517/#source-distributions.

    Should be used as a context manager.
    """

    def __init__(
        self,
        directory: Path,
        name: str,
        version: str,
    ) -> None:
        """Initialize.

        :param directory: The directory to write to.
        :param name: The distribution name.
        :param version: The distribution version.
        """
        self._path = directory / f"{name}-{version}.tar.gz"
        self._dirname = f"{name}-{version}"
        self._fixed_timestamp: t.Optional[int] = None
        try:
            self._fixed_timestamp = int(os.environ["SOURCE_DATE_EPOCH"])
        except (KeyError, ValueError):
            pass
        self._tf: t.Optional[tarfile.TarFile] = None

    @staticmethod
    def raise_not_open() -> t.NoReturn:
        """Assert that the tar file is open."""
        raise IOError("Sdist file is not open.")

    def __enter__(self: SdistWriterType) -> SdistWriterType:
        """Enter the context manager."""
        gz = GzipFile(str(self._path), mode="wb", mtime=self._fixed_timestamp)
        self._tf = tarfile.TarFile(
            str(self._path), mode="w", fileobj=gz, format=tarfile.PAX_FORMAT
        )
        return self

    def __exit__(
        self,
        exc_type: t.Optional[t.Type[BaseException]],
        exc_val: t.Optional[BaseException],
        exc_tb: t.Optional[TracebackType],
    ) -> None:
        """Exit the context manager."""
        if self._tf is None:
            self.raise_not_open()
        self._tf.close()
        if self._tf.fileobj:
            self._tf.fileobj.close()
        self._tf = None

    @property
    def path(self) -> Path:
        """Return the path to the sdist."""
        return self._path

    # methods that require an open tar file

    def list_files(self) -> t.List[str]:
        """Return a list of files in the sdist."""
        if self._tf is None:
            self.raise_not_open()
        return self._tf.getnames()

    def write_text(
        self, path: t.Sequence[str], text: str, encoding: str = "utf-8"
    ) -> None:
        """Write a text file to the sdist.

        :param path: The path to write to in the sdist.
        :param text: The text to write.
        :param encoding: The encoding to use.
        """
        if self._tf is None:
            self.raise_not_open()
        content = text.encode(encoding)
        info = tarfile.TarInfo("/".join((self._dirname, *path)))
        info.size = len(content)
        self._tf.addfile(info, io.BytesIO(content))

    def write_path(
        self,
        path: t.Sequence[str],
        source: Path,
    ) -> None:
        """Write an external path to the sdist.

        :param path: The path to write to in the sdist.
        :param source: The path to write from.
        """
        if self._tf is None:
            self.raise_not_open()
        info = self._tf.gettarinfo(
            str(source), arcname="/".join((self._dirname, *path))
        )
        # make more reproducible
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mode = normalize_file_permissions(info.mode)
        if self._fixed_timestamp is not None:
            info.mtime = self._fixed_timestamp
        if info.isreg():
            with source.open(mode="rb") as handle:
                self._tf.addfile(info, handle)
        else:
            self._tf.addfile(info)
