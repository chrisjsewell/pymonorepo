"""The CLI entrypoint."""
import click


@click.command()
def main() -> None:
    """The pymonorepo CLI."""
    click.echo("Hello World!")


main()
