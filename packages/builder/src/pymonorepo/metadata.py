"""Create the content for the `METADATA` (wheel) of `PKG_INFO` (sdist) file."""
import typing as t
from email.headerregistry import Address
from pathlib import Path

from .analyse import Author, ProjectData


def create_metadata(project: ProjectData, root: Path) -> str:
    """Create the content for the `METADATA` (wheel) of `PKG_INFO` (sdist) file.

    See: https://peps.python.org/pep-0345/

    :project: The project data.
    """
    # required fields
    metadata_text = "Metadata-Version: 2.1\n"
    metadata_text += f"Name: {project['name']}\n"
    metadata_text += f"Version: {project['version']}\n"

    # optional fields
    if "description" in project:
        metadata_text += f"Summary: {project['description']}\n"
    for cat, value in _pep621_people(project.get("authors", [])).items():
        metadata_text += f"{cat}: {value}\n"
    for cat, value in _pep621_people(
        project.get("maintainers", []), "Maintainer"
    ).items():
        metadata_text += f"{cat}: {value}\n"
    if "keywords" in project:
        metadata_text += f"Keywords: {','.join(project['keywords'])}\n"
    for url_name, url in project.get("urls", {}).items():
        metadata_text += f"Project-URL: {url_name}, {url}\n"
    for classifier in project.get("classifiers", []):
        metadata_text += f"Classifier: {classifier}\n"
    if "requires_python" in project:
        metadata_text += f"Requires-Python: {project['requires_python']}\n"
    for req in project.get("dependencies", []):
        metadata_text += f"Requires-Dist: {req}\n"
    for extra, reqs in project.get("optional_dependencies", {}).items():
        metadata_text += f"Provides-Extra: {extra}\n"
        for req in reqs:
            metadata_text += f"Requires-Dist: {req} ; extra == '{extra}'\n"
    readme = project.get("readme", {})
    if "content_type" in readme:
        metadata_text += f"Description-Content-Type: {readme['content_type']}\n"
    if "text" in readme:
        metadata_text += f"\n{readme['text']}\n"
    elif "path" in readme:
        text = (root / readme["path"]).read_text("utf-8")
        metadata_text += f"\n{text}\n"

    metadata_text += "\n"

    return metadata_text


def _pep621_people(
    people: t.List[Author], group_name: str = "Author"
) -> t.Dict[str, str]:
    """Convert authors/maintainers from PEP 621 to core metadata fields"""
    names, emails = [], []
    for person in people:
        if "email" in person:
            email = person["email"]
            if "name" in person:
                email = str(Address(person["name"], addr_spec=email))
            emails.append(email)
        elif "name" in person:
            names.append(person["name"])
    res = {}
    if names:
        res[group_name] = ", ".join(names)
    if emails:
        res[group_name + "-email"] = ", ".join(emails)
    return res


def create_entrypoints(project: ProjectData) -> str:
    """Create the `entry_points.txt` file content.

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
        return entrypoint_text
    return ""
