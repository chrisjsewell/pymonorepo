"""Parse and validate the project metadata from a pyproject.toml file.

See https://www.python.org/dev/peps/pep-0621/, and
https://packaging.python.org/en/latest/specifications/declaring-project-metadata
"""
import typing as t
from pathlib import Path, PurePosixPath

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import NormalizedName, canonicalize_name
from packaging.version import InvalidVersion, Version
from packaging.version import parse as parse_version

__all__ = ("parse", "Pep621Data")


_ALLOWED_FIELDS = {
    "name",
    "version",
    "description",
    "readme",
    "requires-python",
    "license",
    "authors",
    "maintainers",
    "keywords",
    "classifiers",
    "urls",
    "entry-points",
    "scripts",
    "gui-scripts",
    "dependencies",
    "optional-dependencies",
    "dynamic",
}

_ALLOWED_DYNAMIC_FIELDS = _ALLOWED_FIELDS - {"name", "dynamic"}


DYNAMIC_KEY_TYPE = t.Literal[
    "version",
    "description",
    "readme",
    "requires-python",
    "license",
    "authors",
    "maintainers",
    "keywords",
    "classifiers",
    "urls",
    "scripts",
    "gui-scripts",
    "entry-points",
    "dependencies",
    "optional-dependencies",
]

ValidPath = t.NewType("ValidPath", PurePosixPath)
"""A path relative to the project root, delimited by '/',
which does not contain '..',
and points to an existing file with utf8 encoding.
"""


class Author(t.TypedDict, total=False):
    """An author or maintainer."""

    name: str
    email: str


class License(t.TypedDict, total=False):
    """A license for the project."""

    text: str
    path: ValidPath


class Readme(t.TypedDict, total=False):
    """The project's readme."""

    content_type: str
    path: ValidPath
    text: str


class Pep621Data(t.TypedDict, total=False):
    """The validated PEP 621 [project] table from the pyproject.toml file."""

    name: NormalizedName  # TODO ideally this would be t.Required[NormalizedName] in py3.11
    dynamic: t.List[DYNAMIC_KEY_TYPE]
    version: Version
    description: str
    readme: Readme
    licenses: t.List[License]
    keywords: t.List[str]
    classifiers: t.List[str]
    urls: t.Dict[str, str]
    authors: t.List[Author]
    maintainers: t.List[Author]
    requires_python: SpecifierSet
    dependencies: t.List[Requirement]
    optional_dependencies: t.Dict[str, t.List[Requirement]]
    entry_points: t.Dict[str, t.Dict[str, str]]


class ProjectValidationError(Exception):
    """An exception for when a pyproject is invalid."""

    def __init__(self, key: str, code: t.Literal["key", "type", "value"], msg: str):
        """
        :param key: The key that is invalid.
            Nested keys are delimited by `.` and indexes are also added,
            e.g. `project.dynamic.0`.
        :param code: The type of error.
        :param msg: The error message.
        """
        super().__init__(f"{key}: {msg} [{code}]")
        self.key = key
        self.code = code
        self.msg = msg


class ParseResult(t.NamedTuple):
    """The result of parsing the pyproject.toml file."""

    data: Pep621Data
    errors: t.List[ProjectValidationError]


def parse(data: t.Dict[str, t.Any], root: Path) -> ParseResult:
    """Parse and validate the project metadata from a pyproject.toml file,
    according to PEP 621.

    :param data: The data from the pyproject.toml file.
    :param root: The folder containing the pyproject.toml file.
    """
    output: Pep621Data = {"name": canonicalize_name("")}
    errors: t.List[ProjectValidationError] = []

    if "project" not in data:
        errors.append(ProjectValidationError("project", "key", "missing"))
        return ParseResult(output, errors)

    project = data.get("project", {})
    if not isinstance(project, dict):
        errors.append(ProjectValidationError("project", "type", "must be a table"))
        return ParseResult(output, errors)

    # check for unknown keys
    unknown_keys = set(project.keys()) - _ALLOWED_FIELDS
    if unknown_keys:
        for key in unknown_keys:
            errors.append(ProjectValidationError(f"project.{key}", "key", "unknown"))

    # validate dynamic
    if "dynamic" in project:
        output["dynamic"] = []
        if not isinstance(project["dynamic"], list):
            errors.append(
                ProjectValidationError("project.dynamic", "type", "must be an array")
            )
        else:
            for i, item in enumerate(project["dynamic"]):
                if item not in _ALLOWED_DYNAMIC_FIELDS:
                    errors.append(
                        ProjectValidationError(
                            f"project.dynamic.{i}",
                            "value",
                            f"not in allowed fields: {item}",
                        )
                    )
                elif item in project:
                    errors.append(
                        ProjectValidationError(
                            f"project.dynamic.{i}", "value", f"static key found: {item}"
                        )
                    )
                else:
                    output["dynamic"].append(item)

    # validate name
    if "name" in project:
        name = project["name"]
        if not isinstance(name, str):
            errors.append(
                ProjectValidationError("project.name", "type", "must be a string")
            )
        else:
            if not name:
                errors.append(
                    ProjectValidationError("project.name", "value", "must not be empty")
                )
            output["name"] = canonicalize_name(name)
    else:
        errors.append(ProjectValidationError("project.name", "key", "missing"))

    # validate version
    if "version" in project:
        if not isinstance(project["version"], str):
            errors.append(
                ProjectValidationError("project.version", "type", "must be a string")
            )
        else:
            try:
                output["version"] = parse_version(project["version"])
            except InvalidVersion as exc:
                errors.append(
                    ProjectValidationError("project.version", "value", str(exc))
                )
    else:
        if "version" not in output.get("dynamic", []):
            errors.append(
                ProjectValidationError(
                    "project.version", "key", "missing and not in project.dynamic"
                )
            )

    # validate description
    if "description" in project:
        if not isinstance(project["description"], str):
            errors.append(
                ProjectValidationError(
                    "project.description", "type", "must be a string"
                )
            )
        else:
            output["description"] = project["description"]

    # validate readme
    if "readme" in project:
        _parse_readme(project["readme"], root, output, errors)

    # validate license
    if "license" in project:
        if not isinstance(project["license"], dict):
            errors.append(
                ProjectValidationError("project.license", "type", "must be a table")
            )
        else:
            license = project["license"]
            if "file" in license and "text" in license:
                errors.append(
                    ProjectValidationError(
                        "project.license", "key", "cannot have both 'file' and 'text'"
                    )
                )
            if "file" in license:
                valid_path = _validate_file_path(
                    license["file"], "project.license.file", root, errors
                )
                if valid_path is not None:
                    output["licenses"] = [{"path": valid_path}]
            elif "text" in license:
                if not isinstance(license["text"], str):
                    errors.append(
                        ProjectValidationError(
                            "project.license.text", "type", "must be a string"
                        )
                    )
                else:
                    output["licenses"] = [{"text": license["text"]}]
            else:
                errors.append(
                    ProjectValidationError(
                        "project.license", "key", "missing 'file' or 'text'"
                    )
                )

    # validate authors and maintainers
    for authkey in ("authors", "maintainers"):
        if authkey not in project:
            continue
        if not isinstance(project[authkey], list):
            errors.append(
                ProjectValidationError(f"project.{authkey}", "type", "must be an array")
            )
            continue
        output[authkey] = []  # type: ignore
        for i, item in enumerate(project[authkey]):
            if not isinstance(item, dict):
                errors.append(
                    ProjectValidationError(
                        f"project.{authkey}.{i}", "type", "must be a table"
                    )
                )
            elif "name" not in item and "email" not in item:
                errors.append(
                    ProjectValidationError(
                        f"project.{authkey}.{i}", "key", "missing 'name' or 'email'"
                    )
                )
            else:
                unknown_keys = set(item.keys()) - {"name", "email"}
                for key in unknown_keys:
                    errors.append(
                        ProjectValidationError(
                            f"project.{authkey}.{i}.{key}", "key", "unknown"
                        )
                    )
                output[authkey].append(  # type: ignore
                    {key: str(item[key]) for key in ("name", "email") if key in item}
                )

    # validate keywords and classifiers
    for pkey in ("keywords", "classifiers"):
        if pkey not in project:
            continue
        if not isinstance(project[pkey], list):
            errors.append(
                ProjectValidationError(f"project.{pkey}", "type", "must be an array")
            )
        else:
            output[pkey] = []  # type: ignore
            for i, item in enumerate(project[pkey]):
                if not isinstance(item, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.{pkey}.{i}", "type", "must be a string"
                        )
                    )
                else:
                    output[pkey].append(item)  # type: ignore

    # validate urls
    if "urls" in project:
        if not isinstance(project["urls"], dict):
            errors.append(
                ProjectValidationError("project.urls", "type", "must be a table")
            )
        else:
            output["urls"] = {}
            for key, value in project["urls"].items():
                if not isinstance(key, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.urls.{key}", "type", "key must be a string"
                        )
                    )
                    continue
                if not isinstance(value, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.urls.{key}", "type", "value must be a string"
                        )
                    )
                    continue
                output["urls"][key] = value

    # validate requires-python
    if "requires-python" in project:
        if not isinstance(project["requires-python"], str):
            errors.append(
                ProjectValidationError(
                    "project.requires-python", "type", "must be a string"
                )
            )
        else:
            try:
                output["requires_python"] = SpecifierSet(project["requires-python"])
            except InvalidSpecifier as exc:
                errors.append(
                    ProjectValidationError("project.requires-python", "value", str(exc))
                )

    # validate dependencies
    if "dependencies" in project:
        if not isinstance(project["dependencies"], list):
            errors.append(
                ProjectValidationError(
                    "project.dependencies", "type", "must be an array"
                )
            )
        else:
            output["dependencies"] = []
            for i, item in enumerate(project["dependencies"]):
                if not isinstance(item, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.dependencies.{i}", "type", "must be a string"
                        )
                    )
                else:
                    try:
                        output["dependencies"].append(Requirement(item))
                    except InvalidRequirement as exc:
                        errors.append(
                            ProjectValidationError(
                                f"project.dependencies.{i}",
                                "value",
                                str(exc),
                            )
                        )

    # validate optional-dependencies
    if "optional-dependencies" in project:
        if not isinstance(project["optional-dependencies"], dict):
            errors.append(
                ProjectValidationError(
                    "project.optional-dependencies", "type", "must be a table"
                )
            )
        else:
            output["optional_dependencies"] = {}
            for key, value in project["optional-dependencies"].items():
                if not isinstance(key, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.optional-dependencies.{key}",
                            "type",
                            "key must be a string",
                        )
                    )
                    continue
                if not isinstance(value, list):
                    errors.append(
                        ProjectValidationError(
                            f"project.optional-dependencies.{key}",
                            "type",
                            "value must be an array",
                        )
                    )
                    continue
                output["optional_dependencies"][key] = []
                for i, item in enumerate(value):
                    if not isinstance(item, str):
                        errors.append(
                            ProjectValidationError(
                                f"project.optional-dependencies.{key}.{i}",
                                "type",
                                "must be a string",
                            )
                        )
                    else:
                        try:
                            output["optional_dependencies"][key].append(
                                Requirement(item)
                            )
                        except InvalidRequirement as exc:
                            errors.append(
                                ProjectValidationError(
                                    f"project.optional-dependencies.{key}.{i}",
                                    "value",
                                    str(exc),
                                )
                            )

    # validate entry-points
    if "entry-points" in project:
        if not isinstance(project["entry-points"], dict):
            errors.append(
                ProjectValidationError(
                    "project.entry-points", "type", "must be a table"
                )
            )
        else:
            output["entry_points"] = {}
            for key, value in project["entry-points"].items():
                if not isinstance(key, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.entry-points.{key}",
                            "type",
                            "key must be a string",
                        )
                    )
                    continue
                if key in {"console_scripts", "gui_scripts"}:
                    errors.append(
                        ProjectValidationError(
                            f"project.entry-points.{key}", "key", "reserved"
                        )
                    )
                    continue
                if not isinstance(value, dict):
                    errors.append(
                        ProjectValidationError(
                            f"project.entry-points.{key}",
                            "type",
                            "value must be a table",
                        )
                    )
                    continue
                output["entry_points"][key] = {}
                for subkey, subvalue in value.items():
                    if not isinstance(subkey, str):
                        errors.append(
                            ProjectValidationError(
                                f"project.entry-points.{key}.{subkey}",
                                "type",
                                "key must be a string",
                            )
                        )
                        continue
                    if not isinstance(subvalue, str):
                        errors.append(
                            ProjectValidationError(
                                f"project.entry-points.{key}.{subkey}",
                                "type",
                                "value must be a string",
                            )
                        )
                        continue
                    output["entry_points"][key][subkey] = subvalue

    # validate scripts and gui-scripts
    for ekey, ename in (("scripts", "console_scripts"), ("gui-scripts", "gui_scripts")):
        if ekey not in project:
            continue
        if not isinstance(project[ekey], dict):
            errors.append(
                ProjectValidationError(f"project.{ekey}", "type", "must be a table")
            )
        else:
            output.setdefault("entry_points", {})[ename] = {}
            for key, value in project[ekey].items():
                if not isinstance(key, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.{ekey}.{key}", "type", "key must be a string"
                        )
                    )
                    continue
                if not isinstance(value, str):
                    errors.append(
                        ProjectValidationError(
                            f"project.{ekey}.{key}",
                            "type",
                            "value must be a string",
                        )
                    )
                    continue
                output["entry_points"][ename][key] = value

    return ParseResult(output, errors)


def _parse_readme(
    readme: t.Union[str, t.Dict[str, str]],
    root: Path,
    output: Pep621Data,
    errors: t.List[ProjectValidationError],
) -> None:
    """Parse and validate the project readme.

    :param readme: The project readme.
    :param root: The path to the pyproject.toml file.
    :param errors: The list of validation errors.
    """
    if not isinstance(readme, (str, dict)):
        errors.append(
            ProjectValidationError(
                "project.readme", "type", "must be a string or table"
            )
        )
        return

    if isinstance(readme, str):
        valid_path = _validate_file_path(readme, "project.readme", root, errors)
        if valid_path is not None:
            content_type = _guess_readme_mimetype(valid_path)
            output["readme"] = {"path": valid_path}
            if content_type is not None:
                output["readme"]["content_type"] = content_type
        return

    for key in set(readme.keys()) - {"text", "file", "content-type"}:
        errors.append(ProjectValidationError(f"project.readme.{key}", "key", "unknown"))

    content_type = None
    if "content-type" in readme:
        if not isinstance(readme["content-type"], str):
            errors.append(
                ProjectValidationError(
                    "project.readme.content-type", "type", "must be a string"
                )
            )
        else:
            content_type = readme["content-type"]
    else:
        errors.append(
            ProjectValidationError("project.readme.content-type", "key", "missing")
        )

    if "text" in readme and "file" in readme:
        errors.append(
            ProjectValidationError(
                "project.readme",
                "value",
                "table must not contain both 'text' and 'file'",
            )
        )

    if "text" in readme:
        if not isinstance(readme["text"], str):
            errors.append(
                ProjectValidationError(
                    "project.readme.text", "type", "must be a string"
                )
            )
        else:
            output["readme"] = {"text": readme["text"]}
            if content_type is not None:
                output["readme"]["content_type"] = content_type
        return

    if "file" in readme:
        if not isinstance(readme["file"], str):
            errors.append(
                ProjectValidationError(
                    "project.readme.file", "type", "must be a string"
                )
            )
        else:
            valid_path = _validate_file_path(
                readme["file"], "project.readme.file", root, errors
            )
            if valid_path is not None:
                output["readme"] = {"path": valid_path}
                if content_type is not None:
                    output["readme"]["content_type"] = content_type
        return

    errors.append(
        ProjectValidationError(
            "project.readme", "value", "table must contain either 'text' or 'file'"
        )
    )


def _validate_file_path(
    value: str, key: str, root: Path, errors: t.List[ProjectValidationError]
) -> t.Optional[ValidPath]:
    """Validate a relative file path from the project root.

    :param value: A relative path.
    :param key: The key of the path in the project table.
    :param root: The path to the project root.
    :param errors: The list of validation errors. to append to.
    """
    try:
        rel_path = PurePosixPath(value)
    except Exception as exc:
        errors.append(ProjectValidationError(key, "value", f"invalid path: {exc}"))
        return None
    if rel_path.is_absolute():
        errors.append(ProjectValidationError(key, "value", "path must be relative"))
        return None
    if ".." in rel_path.parts:
        errors.append(
            ProjectValidationError(key, "value", "path must not contain '..'")
        )
        return None
    full_path = root / rel_path
    if not full_path.is_file():
        errors.append(
            ProjectValidationError(key, "value", f"file not found: {full_path}")
        )
        return None
    try:
        full_path.read_text("utf-8")
    except Exception as exc:
        errors.append(ProjectValidationError(key, "value", f"file not readable: {exc}"))
    return t.cast(ValidPath, rel_path)


def _guess_readme_mimetype(path: ValidPath) -> t.Optional[str]:
    """Guess the mimetype of the readme.

    :param path: The path to the file.
    """
    suffix = path.suffix.lower()
    if suffix == ".rst":
        return "text/x-rst"
    if suffix == ".md":
        return "text/markdown"
    return None
