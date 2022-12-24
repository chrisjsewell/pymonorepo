"""The main entry module for the PyMonorepo build API."""
import ast
import typing as t
from pathlib import Path

from pymonorepo.pep621 import Author

from .pyproject import parse_pyproject_toml
from .wheel import WheelZip, write_wheel


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
    metadata = parse_pyproject_toml(root)
    project = metadata["project"]
    tool = metadata["tool"]

    # if "projects" in tool, then we are in a workspace otherswise we are in a project
    if "projects" in tool:
        # TODO handle workspace
        # collate all dependencies, requires-python, entrypoints
        raise NotImplementedError("Workspaces not yet implemented")

    # add module
    module_name = tool.get("module", project["name"].replace("-", "_"))
    module_path = None
    for rpath in [root, root / "src"]:
        for mpath in [rpath / module_name, rpath / (module_name + ".py")]:
            if mpath.exists():
                if module_path is not None:
                    raise RuntimeError(
                        f"Multiple possible module paths found: {module_path}, {mpath}"
                    )
                module_path = mpath
    if module_path is None:
        raise RuntimeError(f"Could not find module path for {module_name!r}")

    # find dynamic keys, raise if any unsatisfied
    if "dynamic" in project:
        if "about" in tool:
            mod_info = read_ast_info(tool["about"])
        if module_path.is_dir():
            mod_info = read_ast_info(module_path / "__init__.py")
        else:
            mod_info = read_ast_info(module_path)
        missing = set(project["dynamic"]) - set(mod_info)  # type: ignore
        if missing:
            raise RuntimeError(f"Dynamic keys {missing} not found: {root}")
        for dynamic_key, dynamic_value in mod_info.items():
            if dynamic_key in project["dynamic"]:
                project[dynamic_key] = dynamic_value  # type: ignore

    # write the wheel
    wheel_path = wheel_directory.joinpath(
        f"{project['name']}-{project['version']}-py3-none-any.whl"
    )
    with WheelZip(wheel_path) as wheel:
        write_wheel(wheel, project, {module_name: module_path}, editable=editable)

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


class AstInfo(t.TypedDict, total=False):
    """The information that can be read from a python file."""

    description: str
    version: str
    authors: t.List[Author]


def read_ast_info(path: Path) -> AstInfo:
    """Read information from a python file."""
    if not path.exists():
        raise FileNotFoundError(path)
    # read as bytes to enable custom encodings
    with path.open("rb") as f:
        node = ast.parse(f.read())
    data: t.Dict[str, t.Any] = {}
    docstring = ast.get_docstring(node)
    if docstring:
        data["description"] = docstring
    for child in node.body:
        # Only use if it's a simple string assignment
        if not (isinstance(child, ast.Assign) and isinstance(child.value, ast.Str)):
            continue
        for variable, key in (
            ("__version__", "version"),
            ("__author__", "name"),
            ("__email__", "email"),
        ):
            if any(
                isinstance(target, ast.Name) and target.id == variable
                for target in child.targets
            ):
                data[key] = child.value.s
    author = {}
    if "name" in data:
        author["name"] = data.pop("name")
    if "email" in data:
        author["email"] = data.pop("email")
    if author:
        data["authors"] = [author]
    return t.cast(AstInfo, data)
