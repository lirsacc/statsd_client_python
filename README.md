Python Statsd Client
====================

> :construction: WIP :construction:

This is an implementation of a [Statsd](https://github.com/statsd/statsd) client for Python.

For usage see [documentation](./docs/source/docs.rst).

Motivation
----------

I was looking for a generic Statsd client with tags support to interact with various statsd servers for an application that I distribute but don't operate, so there could be high variability in the statsd implementations used (I know one uses Telegraf and InfluxDB and one Datadog and they both have different tag formats).

- [`pystatsd`](https://statsd.readthedocs.io/en/v3.3/index.html) exists and works, but it [intentionally  does not support tags](https://statsd.readthedocs.io/en/v3.3/tags.html).
- The docs point to [an alternative](https://pypi.org/project/statsd-tags/) supporting tags, but at the time of writing the repository leads to a 404 for me.
- There a are a few more available on PyPi that likely work, but most of the ones I've checked haven't been updated in a while, are not documented and don't support tags.
- [`datadogpy`](https://datadogpy.readthedocs.io/en/latest/) could be a solid solution, but I'd rather avoind pulling the full Datadog client library in projects where I don't use datadog. It also exposes some non standard metric types, and while I can always not use them I'd prefer a generic solution (ignoring tags which, while not standardized, are supported by most statsd servers).

Development
-----------

- All development dependencies are defined in [requirements-dev.txt](./requirements-dev.txt).
- All tests and linting steps are defined in [tox.ini](./tox.ini), you can run the all the checks with `tox`.
- Code is expected to be formatted with `black` and `isort`, you can run the formatters with `tox -e fmt`.
