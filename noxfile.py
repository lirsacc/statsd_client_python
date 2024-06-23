"""
Development tasks.
"""

import shlex
import shutil
from pathlib import Path

import nox


ALL_PYTHON_VERSIONS = (
    "3.8",
    "3.9",
    "3.10",
    "3.11",
    "3.12",
    "pypy3.9",
    "pypy3.10",
)

DEFAULT_PYTHON_VERSION = "3.12"

ROOT_DIR = Path(__file__).parent
REQUIREMENTS_DIR = Path(__file__).parent / "requirements"

DEFAULT_TARGETS = (ROOT_DIR / "src", ROOT_DIR / "tests")
DEFAULT_TEST_TARGETS = (*DEFAULT_TARGETS, ROOT_DIR / "docs")
DEFAULT_LINT_TARGETS = (*DEFAULT_TARGETS, ROOT_DIR / "noxfile.py")

nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv"
nox.options.error_on_external_run = True
nox.options.sessions = (
    "check-imports",
    "lint",
    "mypy",
    "test",
    "coverage",
    "docs",
    "build",
)


@nox.session(python=ALL_PYTHON_VERSIONS, tags=["check"])
def mypy(session: nox.Session) -> None:
    """
    Run the mypy type checker
    """
    session.install("-r", str(REQUIREMENTS_DIR / "lint.txt"))
    session.install("-r", str(REQUIREMENTS_DIR / "test.txt"))
    session.install("-e", str(ROOT_DIR))
    session.run("mypy", *(session.posargs or DEFAULT_TARGETS))


@nox.session(
    python=DEFAULT_PYTHON_VERSION,
    tags=["lint", "check"],
    name="check-imports",
)
def check_imports(session: nox.Session) -> None:
    """
    Check import sort order
    """
    session.install("-r", str(REQUIREMENTS_DIR / "lint.txt"))
    session.run("isort", *(session.posargs or DEFAULT_LINT_TARGETS), "--check")


@nox.session(python=DEFAULT_PYTHON_VERSION, tags=["lint", "check"])
def lint(session: nox.Session) -> None:
    """
    Run the ruff linter
    """
    session.install("-r", str(REQUIREMENTS_DIR / "lint.txt"))
    session.run("ruff", "check", *(session.posargs or DEFAULT_LINT_TARGETS))


@nox.session(python=DEFAULT_PYTHON_VERSION)
def fmt(session: nox.Session) -> None:
    """
    Format the code
    """
    session.install("-r", str(REQUIREMENTS_DIR / "lint.txt"))
    session.run("isort", *(session.posargs or DEFAULT_LINT_TARGETS))
    session.run("ruff", "format", *(session.posargs or DEFAULT_LINT_TARGETS))


@nox.session(python=ALL_PYTHON_VERSIONS, tags=["check"])
def test(session: nox.Session) -> None:
    """
    Run all the tests.
    """
    session.install("-r", str(REQUIREMENTS_DIR / "test.txt"))
    session.install("-e", str(ROOT_DIR))
    session.run(
        "pytest",
        "--showlocals",
        "--cov=statsd",
        "--no-cov-on-fail",
        f"--junit-xml=junit.{session.name}.xml",
        "--cov-report=",
        *(session.posargs or DEFAULT_TEST_TARGETS),
        env={"COVERAGE_FILE": f"coverage.{session.name}"},
    )


@nox.session(python=DEFAULT_PYTHON_VERSION, tags=["check"])
def coverage(session: nox.Session) -> None:
    """
    Generate coverage reports.
    """
    session.install("-r", str(REQUIREMENTS_DIR / "test.txt"))
    session.install("-e", str(ROOT_DIR))
    session.run("coverage", "combine", "--keep", *ROOT_DIR.glob("coverage.*"))
    session.run("coverage", "report")
    session.run("coverage", "html")
    session.run("coverage", "xml")


@nox.session(python=DEFAULT_PYTHON_VERSION, tags=["build"])
def docs(session: nox.Session) -> None:
    session.install("-r", str(REQUIREMENTS_DIR / "docs.txt"))
    session.install("-e", str(ROOT_DIR))
    shutil.rmtree(ROOT_DIR / "docs/build", ignore_errors=True)
    session.run(
        "sphinx-build",
        "-v",
        "-W",
        "-b=html",
        "docs/source",
        "docs/build",
    )


@nox.session(python=DEFAULT_PYTHON_VERSION, tags=["build"])
def build(session: nox.Session) -> None:
    session.install("-r", str(REQUIREMENTS_DIR / "build.txt"))
    shutil.rmtree(ROOT_DIR / "dist", ignore_errors=True)
    session.run("python", "-m", "build", *session.posargs)


@nox.session(python=DEFAULT_PYTHON_VERSION)
def upload(session: nox.Session) -> None:
    session.install("-r", str(REQUIREMENTS_DIR / "build.txt"))
    session.run("twine", "check", "dist/*")
    session.run("twine", "upload", "dist/*")


@nox.session(python=DEFAULT_PYTHON_VERSION)
def deps(session: nox.Session) -> None:
    """
    Ensure requirement files are up to date.

    This can be used to update dependencies, all positional arguments will be
    passed to `uv pip compile ...`.
    """
    session.install("uv")
    for x in REQUIREMENTS_DIR.glob("*.in"):
        session.run(
            "uv",
            "pip",
            "compile",
            "--quiet",
            x.resolve(),
            "--output-file",
            x.with_suffix(".txt"),
            *session.posargs,
            env={
                "UV_CUSTOM_COMPILE_COMMAND": "nox -e deps",
            },
        )


@nox.session(python=DEFAULT_PYTHON_VERSION)
def clean(session: nox.Session) -> None:
    """
    Remove all artifacts and caches.
    """
    for x in [
        'find src tests -type f -name "*.pyc" -delete',
        'find src tests -type f -name "*.pyo" -delete',
        'find src tests -type f -name "*.pyd" -delete',
        'find src tests -type d -name "__pycache__" -delete',
        'find src tests -type f -name "*.c" -delete',
        'find src tests -type f -name "*.so" -delete',
        'find . src tests -type f -path "*.egg-info*" -delete',
        "rm -rf .pytest_cache",
        "rm -rf .mypy_cache",
        'find . -type f -name "junit*.xml" -delete',
        "rm -rf htmlcov",
        'find . -type f -name "coverage*.xml" -delete',
        'find . -type f -name "coverage*" -delete',
        'find . -type f -name "flake8.*" -delete',
        "rm -rf dist build docs/build",
    ]:
        session.run(*shlex.split(x), external=True)
