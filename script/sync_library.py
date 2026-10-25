"""Bundle the iotawattpy-nosignal library fork into the integration.

The bundled copy in custom_components/iotawatt/iotawattpy_nosignal/ is a
generated artefact. Never edit it by hand: change the fork, tag a release,
then run this script.

    script/sync_library.py --ref v0.4.0            # from the local clone
    script/sync_library.py --ref v0.4.0 --remote   # from GitHub
    script/sync_library.py --check                 # CI: verify against GitHub
    script/sync_library.py --dev ../iotawattpy     # local iteration only

Only the standard library is used.
"""

import argparse
from collections.abc import Iterator
import contextlib
import filecmp
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "iotawattpy_nosignal"
BUNDLE_DIR = REPO_ROOT / "custom_components" / "iotawatt" / PACKAGE
SOURCE_FILE = "SOURCE.json"
LICENSE_FILE = "LICENSE"
REMOTE_URL = "https://github.com/No-Signal/iotawattpy"
LOCAL_CLONE = REPO_ROOT.parent / "iotawattpy"


class SyncError(Exception):
    """A sync or check failure with a message for the user."""


def _git(*args: str, cwd: Path | None = None) -> str:
    """Run git and return its stripped stdout."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise SyncError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _is_package_file(relative: Path) -> bool:
    """Return whether a path inside the package belongs in the bundle."""
    if "__pycache__" in relative.parts:
        return False
    return relative.suffix == ".py" or relative.name == "py.typed"


def _bundle_files(source_root: Path) -> dict[str, Path]:
    """Map bundle-relative paths to source files in an exported tree."""
    package = source_root / PACKAGE
    if not (package / "__init__.py").is_file():
        raise SyncError(f"{package} is not the {PACKAGE} package")
    files = {
        path.relative_to(package).as_posix(): path
        for path in sorted(package.rglob("*"))
        if path.is_file() and _is_package_file(path.relative_to(package))
    }
    license_file = source_root / LICENSE_FILE
    if not license_file.is_file():
        raise SyncError(f"{license_file} is missing; the GPL licence must be bundled")
    files[LICENSE_FILE] = license_file
    return files


def _version(source_root: Path) -> str:
    """Return the project version from an exported tree's pyproject.toml."""
    with (source_root / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]["version"]


@contextlib.contextmanager
def _repository(remote: bool, tag: str) -> Iterator[Path]:
    """Yield a git repository that contains the tag."""
    if not remote:
        if not (LOCAL_CLONE / ".git").exists():
            raise SyncError(f"Local clone {LOCAL_CLONE} not found; use --remote")
        yield LOCAL_CLONE
        return
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "repo.git"
        _git("init", "--quiet", "--bare", str(clone))
        try:
            _git(
                "fetch",
                "--quiet",
                "--depth",
                "1",
                REMOTE_URL,
                f"refs/tags/{tag}:refs/tags/{tag}",
                cwd=clone,
            )
        except SyncError as err:
            raise SyncError(f"Tag {tag!r} not found in {REMOTE_URL}: {err}") from None
        yield clone


def _tag_commit(repository: Path, tag: str) -> str:
    """Return the commit a tag points at, refusing anything that isn't a tag."""
    try:
        _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}", cwd=repository)
    except SyncError:
        raise SyncError(f"{tag!r} is not a tag in {repository}") from None
    return _git("rev-parse", f"refs/tags/{tag}^{{commit}}", cwd=repository)


def _export(repository: Path, commit: str, destination: Path) -> None:
    """Export a commit's tree with git archive (never the working tree)."""
    archive = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if archive.returncode:
        raise SyncError(f"git archive failed: {archive.stderr.decode().strip()}")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(destination, filter="data")


def _write_bundle(files: dict[str, Path], source: dict[str, object]) -> None:
    """Replace the bundle directory with the given files and SOURCE.json."""
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    for relative, path in files.items():
        target = BUNDLE_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (BUNDLE_DIR / SOURCE_FILE).write_text(
        json.dumps(source, indent=2) + "\n", encoding="utf-8"
    )


def sync_ref(tag: str, remote: bool) -> None:
    """Bundle the library from a fork tag."""
    with _repository(remote, tag) as repository, tempfile.TemporaryDirectory() as tmp:
        commit = _tag_commit(repository, tag)
        export = Path(tmp)
        _export(repository, commit, export)
        files = _bundle_files(export)
        source = {
            "repository": REMOTE_URL,
            "tag": tag,
            "commit": commit,
            "version": _version(export),
        }
        _write_bundle(files, source)
    print(f"Bundled {PACKAGE} {source['version']} ({tag}, {commit})")


def sync_dev(path: Path) -> None:
    """Bundle the library from a working tree, for local iteration only."""
    path = path.resolve()
    files = _bundle_files(path)
    try:
        commit: str | None = _git("rev-parse", "HEAD", cwd=path)
    except SyncError:
        commit = None
    source = {
        "repository": REMOTE_URL,
        "tag": None,
        "commit": commit,
        "version": _version(path),
        "dirty": True,
    }
    _write_bundle(files, source)
    print(f"Bundled {PACKAGE} from working tree {path} (dev copy, not releasable)")


def _bundled_files() -> dict[str, Path]:
    """Map bundle-relative paths to the currently bundled files."""
    return {
        path.relative_to(BUNDLE_DIR).as_posix(): path
        for path in sorted(BUNDLE_DIR.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.relative_to(BUNDLE_DIR).parts
        and path.name != SOURCE_FILE
    }


def check(remote: bool) -> None:
    """Verify the bundle matches the tag recorded in SOURCE.json."""
    source_path = BUNDLE_DIR / SOURCE_FILE
    if not source_path.is_file():
        raise SyncError(f"{source_path} is missing")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if source.get("dirty") or not source.get("tag"):
        raise SyncError(
            "The bundle is a dev copy (--dev); re-sync from a tag with --ref"
        )
    tag = source["tag"]

    with _repository(remote, tag) as repository, tempfile.TemporaryDirectory() as tmp:
        commit = _tag_commit(repository, tag)
        if commit != source.get("commit"):
            raise SyncError(
                f"Tag {tag} points at {commit}, but SOURCE.json records "
                f"{source.get('commit')}"
            )
        export = Path(tmp)
        _export(repository, commit, export)
        expected = _bundle_files(export)
        if (version := _version(export)) != source.get("version"):
            raise SyncError(
                f"Tag {tag} has version {version}, SOURCE.json records "
                f"{source.get('version')}"
            )
        actual = _bundled_files()

        problems = [
            *(f"missing: {name}" for name in sorted(expected.keys() - actual.keys())),
            *(
                f"unexpected: {name}"
                for name in sorted(actual.keys() - expected.keys())
            ),
            *(
                f"modified: {name}"
                for name in sorted(expected.keys() & actual.keys())
                if not filecmp.cmp(expected[name], actual[name], shallow=False)
            ),
        ]
    if problems:
        raise SyncError(
            f"The bundle differs from {tag} ({commit}):\n  " + "\n  ".join(problems)
        )
    print(f"Bundle matches {tag} ({commit})")


def main() -> int:
    """Run the command line interface."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ref", metavar="TAG", help="bundle this fork tag")
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify the bundle against the tag in SOURCE.json (remote fork)",
    )
    mode.add_argument(
        "--dev", metavar="PATH", type=Path, help="bundle a working tree (local only)"
    )
    location = parser.add_mutually_exclusive_group()
    location.add_argument(
        "--remote", action="store_true", help=f"with --ref, use {REMOTE_URL}"
    )
    location.add_argument(
        "--local",
        action="store_true",
        help=f"with --check, use the local clone {LOCAL_CLONE} (before pushing)",
    )
    args = parser.parse_args()

    if args.remote and not args.ref:
        parser.error("--remote is only valid with --ref")
    if args.local and not args.check:
        parser.error("--local is only valid with --check")

    try:
        if args.ref:
            sync_ref(args.ref, remote=args.remote)
        elif args.check:
            check(remote=not args.local)
        else:
            sync_dev(args.dev)
    except SyncError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
