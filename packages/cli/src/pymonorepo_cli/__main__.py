"""The CLI entrypoint."""
import json
import typing as t
from pathlib import Path

import click
import yaml

from pymonorepo.analyse import analyse_project


class DefaultStrEncoder(json.JSONEncoder):
    """JSON encoder that uses str() for unknown types."""

    def default(self, obj: t.Any) -> t.Union[str, t.List[t.Any]]:
        """Return the string representation of the object."""
        if isinstance(obj, tuple):
            return list(obj)
        return str(obj)


@click.group(context_settings={"help_option_names": ["--help", "-h"]})
def main() -> None:
    """The pymonorepo CLI"""


@main.command()
@click.argument(
    "path", default=".", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
def analyse(path: str) -> None:
    """Analyse a project and show its metadata"""
    proj_config, modules = analyse_project(Path(path))
    proj_config.pop("dynamic", None)  # these have already been resolved
    cleaned = json.loads(
        json.dumps(
            {"project": proj_config, "modules": modules},
            cls=DefaultStrEncoder,
        )
    )
    click.echo(yaml.dump(cleaned, indent=2, sort_keys=False))


main()
