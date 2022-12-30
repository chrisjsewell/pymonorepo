"""Common utilities for files."""
import os
import subprocess
import typing as t
from pathlib import Path


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


def gather_files(
    root: Path,
    *,
    use_git: bool = True,
    allow_non_git: bool = False,
    user_includes: t.Sequence[str] = (),
    user_excludes: t.Sequence[str] = (),
) -> t.Iterable[Path]:
    """Gather all files, using git ls-files to provide a list of tracked files.

    1. Gather all tracked files
    2. Add any user includes
    3. Remove any byte compiled files (__pycache__ folders and .pyc files)
    4. Remove any user excludes

    :return: A list of paths.
    """
    # TODO check this work on Windows?
    if use_git:
        try:
            files = git_tracked_files(root)
        except GitError:
            if allow_non_git:
                files = {p for p in root.glob("**/*") if p.is_file()}
            else:
                raise
    else:
        files = {p for p in root.glob("**/*") if p.is_file()}

    # add any user includes
    for include in user_includes:
        for inc in root.glob(include):
            if inc.is_file():
                files.add(inc)
    # remove any byte compiled files
    files = {f for f in files if "__pycache__" not in f.parts and f.suffix != ".pyc"}
    # remove any user excludes
    for exclude in user_excludes:
        for exc in root.glob(exclude):
            files.discard(exc)
    return sorted(files)


class GitError(Exception):
    """Raised when git fails to run."""


def git_tracked_files(root: Path) -> t.Set[Path]:
    """Get all files tracked by git.

    :raises GitError: If git is not installed or if git ls-files fails.
    """
    try:
        outb = subprocess.check_output(
            ["git", "ls-files", "--recurse-submodules", "-z"],
            cwd=str(root),
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise GitError("Unable to run git ls-files: git not found")
    except subprocess.CalledProcessError as exc:
        raise GitError(f"Unable to run git ls-files in {root}: {exc.stderr.decode()}")
    # TODO flit raises if any untracked/uncommitted files present that are not excluded, do here?
    return {
        root / Path(os.path.normpath(os.fsdecode(loc)))
        for loc in outb.strip(b"\0").split(b"\0")
        if loc
    }
