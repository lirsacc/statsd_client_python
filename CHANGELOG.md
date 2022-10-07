# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2022-10-07

- Add missing `histogram` and ` distribution` metric types.

## [0.3.0] - 2021-08-08

- Add support for float gauge values.

## [0.2.0] - 2020-10-30

- Correctly send a 0 value first when setting a gauge to a negative value.
- Validate metric types.
- Sanitize tag values.
- Handle timedeltas.
- Fix Dogstatsd tag formatter to properly start the block with `|`.
- Specify serializer by passing a `Serializer` instance and not a class.

## [0.1.0] - 2020-10-28

First pass.
