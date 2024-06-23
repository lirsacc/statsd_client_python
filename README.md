Python Statsd Client
====================

> :construction: WIP :construction:

This is an implementation of a [Statsd](https://github.com/statsd/statsd) client
for Python.

For usage see [documentation](./docs/source/docs.rst).

Motivation
----------

I was looking for a generic Statsd client with tags support to interact with
various statsd servers for an application that I distribute but don't operate,
so there could be high variability in the statsd implementations used (I know
one uses Telegraf and InfluxDB and one Datadog and they both have different tag
formats).

- [`pystatsd`](https://statsd.readthedocs.io/en/v3.3/index.html) exists and
  works, but it [intentionally  does not support
  tags](https://statsd.readthedocs.io/en/v3.3/tags.html).
- The docs point to [an alternative](https://pypi.org/project/statsd-tags/)
  supporting tags, but at the time of writing the repository leads to a 404 for
  me.
- There a are a few more available on PyPi that likely work, but most of the
  ones I've checked haven't been updated in a while, are not documented and
  don't support tags.
- [`datadogpy`](https://datadogpy.readthedocs.io/en/latest/) could be a solid
  solution, but I'd rather avoind pulling the full Datadog client library in
  projects where I don't use datadog. It also exposes some non standard metric
  types, and while I can always not use them I'd prefer a generic solution
  (ignoring tags which, while not standardized, are supported by most statsd
  servers).

Development
-----------

### Running with `nox`

You only need [`nox`](https://nox.thea.codes/) installed to run most development
tasks. All tasks are defined in [`noxfile.py`](./noxfile.py) and will run in
individual environments.

Some tasks are defined against multiple python version which are expected to be
available in `$PATH`.

#### Common idioms

- `nox -l` to see all tasks
- `nox -e <TASK>` to run an individual task
- `nox --python <VERSION> ...` to run against a specific python version

### Formatting

Code is expected to be formatted with `ruff` and `isort`. You can run the
formatters with `nox -e fmt`.

### Dependencies

All dependencies are locked using [`uv`](https://github.com/astral-sh/uv). You
can recompile all of them or update specific packages by using:

    nox -e deps -- <UV_ARGS> ...

### Running in your own virtualenv

To run all the tooling directly in a manually managed virtualenv or in your IDE,
you can install all development dependencies through
[requirements-dev.txt](./requirements-dev.txt):

    $ pip install -r requirements-dev.txt

After which all tools (`ruff`, `isort`, `pytest`, etc.) will be available.

### pre-commit

If this suits your workflow, you can install the pre-commit configuration using `pre-commit install` which will automatically check some things before allowing you to commit (`pre-commit` is included in the dev dependencies).
