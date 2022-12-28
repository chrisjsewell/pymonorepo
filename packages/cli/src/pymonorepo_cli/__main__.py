"""The CLI entrypoint."""
import json
import typing as t
from pathlib import Path

import build.__main__ as build_cli
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


@main.command("build")
@click.argument(
    "srcdir", default=".", type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
@click.option(
    "-o",
    "--outdir",
    default=None,
    type=click.Path(file_okay=False, dir_okay=True),
    help="output directory (defaults to {srcdir}/dist)",
)
@click.option(
    "-s",
    "--sdist",
    is_flag=True,
    default=False,
    help="build a source distribution only",
)
@click.option(
    "-w", "--wheel", is_flag=True, default=False, help="build a wheel distribution only"
)
@click.option(
    "--isolation/--no-isolation",
    default=True,
    help="isolate the build in a virtual environment",
)
def _build(
    srcdir: str, outdir: t.Optional[str], wheel: bool, sdist: bool, isolation: bool
) -> None:
    """Build a project"""
    srcpath = Path(srcdir)
    if outdir is None:
        outpath = srcpath / "dist"
    else:
        outpath = Path(outdir)
    if wheel or sdist:
        distributions = []
        if wheel:
            distributions.append("wheel")
        if sdist:
            distributions.append("sdist")
    else:
        distributions = ["wheel", "sdist"]
    build_cli.build_package(srcpath, outpath, distributions, isolation=isolation)


# TODO: add commands; init, publish, etc.

main()
