#!/usr/bin/env python
# -*- coding: utf-8 -*-
# mypy: ignore-errors

import os

import setuptools

DIR = os.path.abspath(os.path.dirname(__file__))


def run_setup():

    with open(os.path.join(DIR, "README.md")) as f:
        readme = "\n" + f.read()

    setuptools.setup(
        name="statsd_python",
        version=_get_version(os.path.join(DIR, "src", "statsd", "version.py")),
        description="",
        long_description=readme,
        long_description_content_type="text/markdown",
        author="Charles Lirsac",
        author_email="c.lirsac@gmail.com",
        url="https://github.com/lirsacc/statsd_client_python",
        license="MIT",
        keywords="statsd metrics",
        zip_safe=False,
        packages=setuptools.find_packages(where="src"),
        package_dir={"": "src"},
        install_requires=[],
        include_package_data=True,
        python_requires=">=3.6",
        classifiers=[
            "Development Status :: 4 - Beta",
            "Intended Audience :: Developers",
            "Natural Language :: English",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
            "Programming Language :: Python",
            "Programming Language :: Python :: 3 :: Only",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Typing :: Typed",
            "Topic :: Software Development :: Libraries",
            "Topic :: Software Development :: Libraries :: Python Modules",
        ],
        project_urls={
            "Bug Reports": "https://github.com/lirsacc/statsd_client_python/issues",
            "Source": "https://github.com/lirsacc/statsd_client_python",
        },
    )


def _get_version(path):
    with open(path) as f:
        for line in f.readlines():
            if line.startswith("__version__"):
                delim = '"' if '"' in line else "'"
                return line.split(delim)[1]
        else:
            raise RuntimeError("Unable to find version string.")


if __name__ == "__main__":
    run_setup()
