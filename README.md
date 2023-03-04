# pymonorepo

NOTE: This package is not intended for production use (at least yet).
It is a protype to test out how a monorepo tool might look in Python.

A Python package build tool for handling [monorepos](https://en.wikipedia.org/wiki/Monorepo).

> A monorepo is a software-development strategy in which the code for a number of projects is stored in the same repository

Moreso than simply housing a number of "unrelated" projects,
I would suggest that a monorepo's intention is to build relations between these packages,
for example, having shared dependecies and/or depending on one another.

Outside of Python, examples of monorepo tools are:

- https://docs.npmjs.com/cli/v7/using-npm/workspaces
- https://doc.rust-lang.org/book/ch14-03-cargo-workspaces.html

At present, to my knowledge, there is no such "defacto" tool in the Python ecosytem
(see e.g. https://github.com/pypa/hatch/issues/233)

## Usage

You can see how this looks in this repos [pyproject.toml](./pyproject.toml):

The build backend is set as:

```toml
[build-system]
requires = ["packaging>=22", "tomli; python_version<'3.11'"]
build-backend = "pymonorepo.backend"
```

and workspaces are added with:

```
[tool.monorepo.workspace]
packages = ["packages/*"]
```

When build, e.g. with `pip install -e .`,
all workspaces are "combined" to build a single `wheel` or `sdist`
