"""Analyse a project"""
import ast
import typing as t
from dataclasses import dataclass, field
from functools import reduce
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.utils import NormalizedName

from ._pep621 import Author, License, PyProjectData, ValidPath
from ._pyproject import PyMetadata, ToolMetadata, parse_pyproject_toml


@dataclass
class ProjectAnalysis:
    """Result of analysing a project."""

    root: Path
    """The root of the project."""
    is_workspace: bool
    """Whether the project is a workspace."""
    project: PyProjectData
    """The resolved project data."""
    tool: ToolMetadata
    """The resolved tool.pymonorepo data."""
    modules: t.Dict[str, Path]
    """The modules in the project."""
    graph: t.Dict[str, t.Set[Requirement]] = field(default_factory=dict)
    """The dependency graph of the workspace."""

    @property
    def name(self) -> NormalizedName:
        """The kebab case name of the project."""
        return self.project["name"]

    @property
    def snake_name(self) -> str:
        """The snake case name of the project."""
        return self.project["name"].replace("-", "_")


def analyse_workspace(root: Path, metadata: PyMetadata) -> ProjectAnalysis:
    """Analyse a workspace folder."""
    proj_config = metadata["project"]
    tool_config = metadata["tool"]
    wspace_config = tool_config["workspace"]

    required_dynamic = {
        "license",
        "requires-python",
        "dependencies",
        "entry-points",
        "scripts",
        "gui-scripts",
    }
    proj_dynamic = set(proj_config.get("dynamic", []))
    if proj_dynamic != required_dynamic:
        raise RuntimeError(
            f"Workspace must have dynamic keys: {required_dynamic}, got {proj_dynamic}"
        )

    # read all packages first
    packages: t.Dict[str, ProjectAnalysis] = {}
    for pkg_path in wspace_config.get("packages", []):
        # TODO check all packages have the same build-backend as the workspace?
        analysis = analyse_project(pkg_path, in_workspace=True)
        if analysis.name in packages:
            other_path = packages[analysis.name].root
            raise RuntimeError(
                f"Duplicate package name: {analysis.project['name']!r} in "
                f"'{pkg_path}' and '{other_path}'"
            )
        packages[analysis.name] = analysis

    # collate licence paths
    licenses: t.List[License] = []
    for pkg_path, license in [
        (pkg.root, li)
        for pkg in packages.values()
        for li in pkg.project.get("licenses", [])
    ]:
        if "path" not in license:
            continue
        license_path = pkg_path / license["path"]
        licenses.append(
            {
                "path": t.cast(
                    ValidPath,
                    PurePosixPath(license_path.relative_to(root).as_posix()),
                )
            }
        )
    if licenses:
        proj_config["licenses"] = licenses

    # collate python version requirement
    requires_python = [
        pkg.project["requires_python"]
        for pkg in packages.values()
        if "requires_python" in pkg.project
    ]
    if requires_python:
        proj_config["requires_python"] = reduce(lambda a, b: a & b, requires_python)

    # collate entry points
    entry_points: t.Dict[str, t.Dict[str, str]] = {}
    groups = {
        name
        for pkg in packages.values()
        for name in pkg.project.get("entry_points", {})
    }
    for group in groups:
        # check for conflicts and report the package that defines the conflicting entry point
        points: t.Dict[str, t.Tuple[str, Path]] = {}
        for pkg in packages.values():
            if group not in pkg.project.get("entry_points", {}):
                continue
            for point_name, point in pkg.project["entry_points"][group].items():
                if point_name in points:
                    other_pkg = points[point_name][1]
                    raise RuntimeError(
                        f"Entry point '{group}.{point_name}' defined in both"
                        f" '{other_pkg}' and '{pkg.root}'"
                    )
                points[point_name] = (point, pkg.root)
        if points:
            entry_points[group] = {name: point for name, (point, _) in points.items()}
    if entry_points:
        proj_config["entry_points"] = entry_points

    # collate modules
    modules: t.Dict[str, Path] = {}
    for pkg in packages.values():
        for module_name, module_path in pkg.modules.items():
            if module_name in modules:
                other_path = modules[module_name]
                raise RuntimeError(
                    f"Module {module_name!r} defined in both"
                    f" '{other_path}' and '{module_path}'"
                )
            modules[module_name] = module_path

    # collate dependencies
    package_graph: t.Dict[str, t.Set[Requirement]] = {}
    dependencies: t.List[Requirement] = []
    for pkg in packages.values():
        package_graph[pkg.name] = set()
        pkg_extras = pkg.project.get("optional_dependencies", {})
        for dep in pkg.project.get("dependencies", []):
            if dep.name in packages:
                if not dep.specifier.contains(packages[dep.name].project["version"]):
                    raise RuntimeError(
                        f"Dependency '{dep.name}' version '{dep.specifier}' does not match "
                        f"workspace version '{packages[dep.name].project['version']!r}': {pkg.root}"
                    )
                for extra in dep.extras:
                    if extra not in pkg_extras:
                        raise RuntimeError(
                            f"Dependency '{dep.name}' extra '{extra}' not defined: {pkg.root}"
                        )
                    for extra_dep in pkg_extras[extra]:
                        if extra_dep.name in packages:
                            # TODO allow for package dependencies in extras
                            raise NotImplementedError(
                                f"Dependency '{dep.name}' extra '{extra}' "
                                f"contains a package: {pkg.root}"
                            )
                        else:
                            dependencies.append(extra_dep)
                package_graph[pkg.name].add(dep)
            else:
                dependencies.append(dep)
    if dependencies:
        proj_config["dependencies"] = reduce_dependencies(dependencies)

    # collate sdist include/exclude
    # TODO deal with sdist.use_git
    for pkg in packages.values():
        for clude_name in ("include", "exclude"):
            cludes: t.List[str] = pkg.tool.get("sdist", {}).get(clude_name, [])  # type: ignore
            rel_cludes = [
                (pkg.root.relative_to(root).as_posix() + "/" + clude)
                for clude in cludes
            ]
            if rel_cludes:
                clude_config = tool_config.setdefault("sdist", {}).setdefault(  # type: ignore
                    clude_name, []
                )
                clude_config.extend(rel_cludes)

    return ProjectAnalysis(
        root=root,
        project=proj_config,
        tool=tool_config,
        modules=modules,
        is_workspace=True,
        graph=package_graph,
    )


def reduce_dependencies(deps: t.List[Requirement]) -> t.List[Requirement]:
    """Reduce a list of dependencies, compacting duplicates and merging extras/specifiers."""
    new_deps: t.Dict[t.Hashable, Requirement] = {}
    for dep in deps:
        unique = (dep.name, dep.url, dep.marker)
        if unique not in new_deps:
            new_deps[unique] = dep
        else:
            new_deps[unique].specifier &= dep.specifier
            new_deps[unique].extras |= dep.extras

    # TODO simplify and validate specifiers
    # e.g. if '>1,>2' then '>2'
    # e.g. if '>1,<2' then error

    return list(new_deps.values())


def analyse_project(root: Path, in_workspace: bool = False) -> ProjectAnalysis:
    """Analyse a project folder."""
    metadata = parse_pyproject_toml(root)
    proj_config = metadata["project"]
    tool_config = metadata["tool"]

    if "workspace" in tool_config:
        if in_workspace:
            raise RuntimeError(f"Workspaces cannot contain other workspaces: {root}")
        return analyse_workspace(root, metadata)

    pkg_config = tool_config.get("package", {})

    # find module
    if "module" in pkg_config:
        module_path = root / pkg_config["module"]
        module_name = module_path.name if module_path.is_dir() else module_path.stem
    else:
        module_name = proj_config["name"].replace("-", "_")
        module_path = None
        for mpath in [
            root / module_name,
            root / "src" / module_name,
            root / (module_name + ".py"),
            root / "src" / (module_name + ".py"),
        ]:
            if mpath.exists():
                module_path = mpath
                break

    # find dynamic keys, raise if any unsatisfied
    if "dynamic" in proj_config:

        if "about" in pkg_config:
            mod_info = read_ast_info(root / pkg_config["about"])
        elif module_path and module_path.is_dir():
            mod_info = read_ast_info(module_path / "__init__.py")
        elif module_path:
            mod_info = read_ast_info(module_path)
        else:
            mod_info = {}
        missing = set(proj_config["dynamic"]) - set(mod_info)  # type: ignore
        if missing:
            raise KeyError(f"Dynamic keys {missing} not found: {root}")
        for dynamic_key, dynamic_value in mod_info.items():
            if dynamic_key in proj_config["dynamic"]:
                proj_config[dynamic_key] = dynamic_value  # type: ignore

    return ProjectAnalysis(
        root=root,
        project=proj_config,
        tool=tool_config,
        modules={module_name: module_path} if module_path else {},
        is_workspace=False,
    )


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
