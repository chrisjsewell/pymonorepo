"""Create the content for the `METADATA` (wheel) of `PKG_INFO` (sdist) file."""
import typing as t
from email.headerregistry import Address

from .pep621 import Author, ProjectData


def create_metadata(project: ProjectData) -> str:
    """Create the content for the `METADATA` (wheel) of `PKG_INFO` (sdist) file.

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
    if "readme_content_type" in project:
        metadata_text += f"Description-Content-Type: {project['readme_content_type']}\n"
    if "readme_text" in project:
        metadata_text += f"\n{project['readme_text']}\n"

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
