"""Read the pyproject.toml file, parse and validate it."""
import typing as t
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from ._pep621 import ProjectData, VError
from ._pep621 import parse as parse_project

TOOL_SECTION = "monorepo"


def read_pyproject_toml(path: Path) -> t.Dict[str, t.Any]:
    """Read the pyproject.toml file.

    :returns: The contents of the pyproject.toml file.
    """
    return tomllib.loads(path.read_text("utf-8"))  # type: ignore[no-any-return]


class PyMetadata(t.TypedDict):
    """The parsed pyproject.toml file."""

    project: ProjectData
    tool: "ToolMetadata"


def parse_pyproject_toml(root: Path) -> PyMetadata:
    """Read the pyproject.toml file, parse and validate it."""
    pyproject_file = root.joinpath("pyproject.toml")
    if not pyproject_file.exists():
        raise FileNotFoundError(pyproject_file)
    metadata = read_pyproject_toml(pyproject_file)
    # parse and validate the project configuration
    project_result = parse_project(metadata, root)
    # parse and validate the tool configuration
    tool_result = parse_tool(metadata, root)

    errors = project_result.errors + tool_result.errors
    if errors:
        raise RuntimeError(
            "Error(s) parsing {0}:\n{1}".format(
                pyproject_file,
                "\n".join(f"- [{e.key}]:{e.etype}: {e.msg}" for e in errors),
            )
        )

    return {"project": project_result.data, "tool": tool_result.data}


class ToolMetadata(t.TypedDict, total=False):
    """The parsed tool configuration."""

    workspace: "WorkspaceMetadata"
    """The workspace configuration."""
    package: "PackageMetadata"
    """The package configuration."""


class PackageMetadata(t.TypedDict, total=False):
    module: PurePosixPath
    """The module name of the project, otherwise inferred from the project name."""
    about: PurePosixPath
    """Python file to read dynamic info from, otherwise inferred from module."""


class WorkspaceMetadata(t.TypedDict, total=False):
    """The workspace configuration."""

    packages: t.List[Path]
    """The list of packages in the workspace."""


class ParseToolResult(t.NamedTuple):
    """The parsed tool configuration."""

    data: ToolMetadata
    errors: t.List[VError]


def parse_tool(metadata: t.Dict[str, t.Any], root: Path) -> ParseToolResult:
    """Parse the tool configuration."""
    result = ParseToolResult({}, [])

    tool = metadata.get("tool", {})
    if not isinstance(tool, dict):
        result.errors.append(VError("tool", "type", "must be a table"))
        return result

    config = tool.get(TOOL_SECTION, {})
    if not isinstance(config, dict):
        result.errors.append(VError(f"tool.{TOOL_SECTION}", "type", "must be a table"))
        return result

    if "workspace" in config and "package" in config:
        result.errors.append(
            VError(
                f"tool.{TOOL_SECTION}",
                "key",
                "cannot contain both 'workspace' and 'package'",
            )
        )

    if "workspace" in config:
        if not isinstance(config["workspace"], dict):
            result.errors.append(
                VError(f"tool.{TOOL_SECTION}.workspace", "type", "must be a table")
            )
        else:
            wresult = parse_workspace(config["workspace"], root)
            result.data["workspace"] = wresult[0]
            result.errors.extend(wresult[1])

    if "package" in config:
        if not isinstance(config["package"], dict):
            result.errors.append(
                VError(f"tool.{TOOL_SECTION}.package", "type", "must be a table")
            )
        else:
            presult = parse_package(config["package"], root)
            result.data["package"] = presult[0]
            result.errors.extend(presult[1])

    return result


def parse_workspace(
    config: t.Dict[str, t.Any], root: Path
) -> t.Tuple[WorkspaceMetadata, t.List[VError]]:
    """Parse the package configuration."""
    result: WorkspaceMetadata = {}
    errors: t.List[VError] = []

    if not isinstance(config.get("packages", []), list):
        errors.append(VError(f"tool.{TOOL_SECTION}.packages", "type", "must be a list"))
    elif config.get("packages"):
        result["packages"] = []
        for idx, project in enumerate(config.get("packages", [])):
            if not isinstance(project, str):
                errors.append(
                    VError(
                        f"tool.{TOOL_SECTION}.packages.{idx}",
                        "type",
                        "must be a string",
                    )
                )
                continue
            if Path(project).is_absolute():
                errors.append(
                    VError(
                        f"tool.{TOOL_SECTION}.packages.{idx}",
                        "value",
                        "must be a relative path",
                    )
                )
                continue
            packages = [p for p in root.glob(project) if p.is_dir()]
            if not packages:
                errors.append(
                    VError(
                        f"tool.{TOOL_SECTION}.packages.{idx}",
                        "value",
                        "no matching directories found",
                    )
                )
                continue
            result["packages"].extend(packages)

    return result, errors


def parse_package(
    config: t.Dict[str, t.Any], root: Path
) -> t.Tuple[PackageMetadata, t.List[VError]]:
    """Parse the package configuration."""
    result: PackageMetadata = {}
    errors: t.List[VError] = []

    if "module" in config:
        mod_path = _validate_path(
            config["module"], f"tool.{TOOL_SECTION}.module", root, errors
        )
        if mod_path is not None:
            result["module"] = mod_path

    if "about" in config:
        about_path = _validate_path(
            config["about"], f"tool.{TOOL_SECTION}.about", root, errors
        )
        if about_path is not None:
            result["about"] = about_path

    return result, errors


def _validate_path(
    value: str, key: str, root: Path, errors: t.List[VError]
) -> t.Optional[PurePosixPath]:
    """Validate a relative file path from the project root.

    :param value: A relative path.
    :param key: The key of the path in the project table.
    :param root: The path to the project root.
    :param errors: The list of validation errors. to append to.
    """
    if not isinstance(value, str):
        errors.append(VError(key, "type", "must be a string"))
        return None
    try:
        rel_path = PurePosixPath(value)
    except Exception as exc:
        errors.append(VError(key, "value", f"invalid path: {exc}"))
        return None
    if rel_path.is_absolute():
        errors.append(VError(key, "value", "path must be relative"))
        return None
    if ".." in rel_path.parts:
        errors.append(VError(key, "value", "path must not contain '..'"))
        return None
    full_path = root / rel_path
    if not full_path.exists():
        errors.append(VError(key, "value", f"path not found: {full_path}"))
        return None
    return rel_path
