"""Read the pyproject.toml file, parse and validate it."""
import typing as t
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from .pep621 import ProjectData, VError
from .pep621 import parse as parse_project

TOOL_SECTION = "pymonorepo"


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
            "Error(s) parsing pyproject.toml:\n%s"
            % "\n".join(f"[{e.key}]:{e.etype}: {e.msg}" for e in errors)
        )

    return {"project": project_result.data, "tool": tool_result.data}


class ToolMetadata(t.TypedDict, total=False):
    """The parsed tool configuration."""

    projects: t.List[Path]
    """The list of projects in the workspace."""
    module: str
    """The module name of the project, otherwise inferred from the project name."""
    about: Path
    """Python file to read dynamic info from, otherwise inferred from module."""


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

    if "module" in config:
        if not isinstance(config["module"], str):
            result.errors.append(
                VError(f"tool.{TOOL_SECTION}.module", "type", "must be a string")
            )
        else:
            result.data["module"] = config["module"]

    if "about" in config:
        if not isinstance(config["about"], str):
            result.errors.append(
                VError(f"tool.{TOOL_SECTION}.about", "type", "must be a string")
            )
        elif Path(config["about"]).is_absolute():
            result.errors.append(
                VError(
                    f"tool.{TOOL_SECTION}.about",
                    "value",
                    "must be a relative path",
                )
            )
        else:
            result.data["about"] = root / Path(config["about"])

    if not isinstance(config.get("projects", []), list):
        result.errors.append(
            VError(f"tool.{TOOL_SECTION}.projects", "type", "must be a list")
        )
    elif config.get("projects"):
        result.data["projects"] = []
        for idx, project in enumerate(config.get("projects", [])):
            if not isinstance(project, str):
                result.errors.append(
                    VError(
                        f"tool.{TOOL_SECTION}.projects.{idx}",
                        "type",
                        "must be a string",
                    )
                )
                continue
            if Path(project).is_absolute():
                result.errors.append(
                    VError(
                        f"tool.{TOOL_SECTION}.projects.{idx}",
                        "value",
                        "must be a relative path",
                    )
                )
                continue
            projects = [p for p in root.glob(project) if p.is_dir()]
            if not projects:
                result.errors.append(
                    VError(
                        f"tool.{TOOL_SECTION}.projects.{idx}",
                        "value",
                        "no matching directories found",
                    )
                )
                continue
            result.data["projects"].extend(projects)

    return result
