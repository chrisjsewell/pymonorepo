# pymonorepo

A Python package build tool for handling monorepos.

The key features are:

- Build a single distribution containing all projects in the monorepo.


- https://docs.npmjs.com/cli/v7/using-npm/workspaces
- https://doc.rust-lang.org/book/ch14-03-cargo-workspaces.html


## Requirements

A monorepo is identified by a `pyproject.toml` file at the root of the repository.
This file must contain a `[tools.workspace]` table with the `projects` key.

1. When called from the root of a monorepo, should build a distribution containing all projects.
   - Projects are by default all
