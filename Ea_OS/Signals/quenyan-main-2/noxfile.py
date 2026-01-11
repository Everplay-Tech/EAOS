from __future__ import annotations

import os
import pathlib
import secrets
from typing import Iterable

import nox

ROOT = pathlib.Path(__file__).parent
CONSTRAINTS = ROOT / "requirements-dev.lock"

nox.options.sessions = ["lint", "typecheck", "tests", "property", "coverage"]
nox.options.reuse_existing_virtualenvs = False
nox.options.error_on_missing_interpreters = True


def install_with_constraints(session: nox.Session, *args: str) -> None:
    if not CONSTRAINTS.exists():
        session.error("Constraints file missing; generate it with `nox -s lock`.")
    session.install(f"--constraint={CONSTRAINTS}", *args)


@nox.session(python=["3.10", "3.11", "3.12"])
def tests(session: nox.Session) -> None:
    install_with_constraints(session, "coverage[toml]", "pytest", "hypothesis", ".")
    session.env["PYTHONHASHSEED"] = os.environ.get(
        "PYTHONHASHSEED", str(secrets.randbits(32))
    )
    session.run("coverage", "run", "-m", "pytest", "-vv", "--strict-markers", *session.posargs)


@nox.session(python=["3.10", "3.11", "3.12"])
def property(session: nox.Session) -> None:
    install_with_constraints(session, "pytest", "hypothesis", ".")
    session.env["PYTHONHASHSEED"] = os.environ.get(
        "PYTHONHASHSEED", str(secrets.randbits(32))
    )
    session.run("pytest", "-vv", "-m", "property", "--strict-markers", *session.posargs)


@nox.session(python=["3.10", "3.11", "3.12"])
def lint(session: nox.Session) -> None:
    install_with_constraints(session, "ruff", "flake8")
    session.run("ruff", "check", "qyn1", "tests")
    session.run("flake8", "qyn1", "tests")


@nox.session(python=["3.10", "3.11", "3.12"])
def typecheck(session: nox.Session) -> None:
    install_with_constraints(session, "mypy", ".")
    session.run("mypy", "qyn1")


@nox.session(python="3.10")
def coverage(session: nox.Session) -> None:
    install_with_constraints(session, "coverage")
    session.run("coverage", "combine")
    session.run("coverage", "report", "--fail-under=80")
    session.run("coverage", "xml", "-o", "coverage.xml")
    session.run("coverage", "html")


@nox.session(python="3.10")
def audit(session: nox.Session) -> None:
    install_with_constraints(session, "pip-audit")
    session.run("pip-audit", "-r", str(CONSTRAINTS))


@nox.session(python="3.10")
def sbom(session: nox.Session) -> None:
    install_with_constraints(session, "cyclonedx-bom")
    output = ROOT / "sbom.json"
    session.run("cyclonedx-bom", "-o", str(output), "-e", "-i", "pyproject.toml", external=True)


@nox.session(python="3.10")
def build(session: nox.Session) -> None:
    install_with_constraints(session, "build", "twine", ".")
    session.run("python", "-m", "build", "--wheel", "--sdist")
    session.run("twine", "check", "dist/*")


@nox.session(python="3.10")
def sign(session: nox.Session) -> None:
    install_with_constraints(session, "sigstore")
    artifacts: Iterable[str] = [str(p) for p in (ROOT / "dist").glob("*")]
    if not artifacts:
        session.error("No artifacts found in dist/. Run `nox -s build` first.")
    id_token = session.env.get("SIGSTORE_ID_TOKEN", "")
    session.log("Signing artifacts with Sigstore")
    session.run("sigstore", "sign", *artifacts, *(["--identity-token", id_token] if id_token else []))


@nox.session(python="3.10")
def lock(session: nox.Session) -> None:
    install_with_constraints(session, "pip-tools")
    session.run(
        "pip-compile",
        "--extra",
        "dev",
        "pyproject.toml",
        "--output-file",
        str(CONSTRAINTS),
        "--resolver=backtracking",
    )


@nox.session(python="3.10")
def lockcheck(session: nox.Session) -> None:
    install_with_constraints(session, "pip-tools")
    session.run(
        "pip-compile",
        "--quiet",
        "--no-upgrade",
        "--extra",
        "dev",
        "pyproject.toml",
        "--output-file",
        str(CONSTRAINTS),
        "--resolver=backtracking",
    )
    session.run("git", "diff", "--quiet", str(CONSTRAINTS), external=True)
