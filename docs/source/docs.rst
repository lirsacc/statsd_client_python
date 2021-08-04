Documentation
=============

Installation
------------

This library is released on `PyPI <https://pypi.org/project/statsd-python/>`_ and
can be installed through pip:

.. code:: python

    pip install statsd-python

Usage
-----

.. code:: python

    from statsd import StatsdClient

    # Create a UDP based client with default connection parameters.
    client = StatsdClient()

    client.increment('my-counter')  # Increment my-counter by one
    client.gauge('my-gauge', 42, sample_rate=.5)  # Set a gauge value, sampling only half of the events

Metric types
~~~~~~~~~~~~

:class:`~statsd.StatsdClient` supports all metric types `defined by
Statsd <https://github.com/statsd/statsd>`_:

- Counters track the total number of occurrences of a given event.

.. code:: python

    client.increment('my-counter')
    client.decrement('my-counter', 3)

- Gauges track a value over time.

.. code:: python

    # Set the value
    client.gauge('my-gauge', 42)
    # Deltas are supported as well
    client.gauge('my-gauge', 3, is_update=True)
    client.gauge('my-gauge', -1, is_update=True)

.. warning::

    Some Statsd servers implementations (such as `Datadog's
    <https://github.com/DataDog/dd-agent/issues/573>`_)  do not support
    gauge deltas.

- Timings are used track durations in milliseconds.

.. code:: python

    # Measure a duration of 1.234 seconds
    client.timing('my-duration', 1234)

The library also includes helpers for measuring code execution time using
:py:func:`~time.perf_counter`.

.. code:: python

    @timed('my-duration')
    def do_something():
        pass

    with timer('my-duration'):
        do_some_other_thing()

- Sets count unique occurences per key

.. code:: python

    # Record one occurence of `my-set` for the key 1234.
    client.set('my-set', 1234)

Sampling
~~~~~~~~

All the metrics accept a ``sample_rate`` parameter. This should be a float
between 0 and 1 that the client will use to sample metrics. By default all
metrics are sent with a sample rate of 1 (no sampling). The client will
include this information in metric packets so the server can handle this
accordingly.

.. code:: python

    # Only send the metric half the time.
    client.gauge('my-gauge', 42, sample_rate=0.5)
    # Only send the metric 75% of the time.
    client.gauge('my-gauge', 42, sample_rate=0.25)
    # Only send the metric 25% of the time.
    client.gauge('my-gauge', 42, sample_rate=0.75

Tag support
~~~~~~~~~~~

Tags are supported. All metrics will accept a dictionnary for tags.

Different server implementations will accept different ways to include tags in
the metric packets so this library exposes a mechanism to configure this
beheaviour through the :mod:`statsd.format` module.

By default the `Dogstatsd
<https://docs.datadoghq.com/developers/dogstatsd/datagram_shell/>`_ format is
used. To customise this callers just need to instantiate the
:class:`~statsd.StatsdClient` with the right parameters:

.. code:: python

    from statsd import StatsdClient
    from statsd.formats import TelegrafSerializer

    client = StatsdClient(serializer=TelegrafSerializer()

Transports
~~~~~~~~~~

For now a single transport is currently supported through
:class:`~statsd.StatsdClient` / :class:`~statsd.UDPStatsdClient`.


Debug client
~~~~~~~~~~~~

The :class:`~statsd.DebugStatsdClient` exposes a verbose client which can be
swapped out for the real thing in development or when logging metrics is useful.

The client can be used as-is to just forward all metrics to a logger:

.. code:: python

    import logging
    from statsd import DebugStatsdClient

    client = DebugStatsdClient(
        # By default the logger instance named `statsd` is managed by the
        # library but you can pass in any logger instance
        logger=logging.getLogger('debug-metrics'),
    )

The debug client can also be used to wrap an existing client:

.. code:: python

    from django.conf import settings
    from statsd import DebugStatsdClient, StatsdClient

    client = StatsdClient()

    if settings.DEBUG:
        client = DebugStatsdClient(inner=client)
