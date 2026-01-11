"""Command line interface for the Quenyan toolchain."""

from __future__ import annotations

import argparse
import ast
import json
import os
import secrets
import sys
import textwrap
import time

from dataclasses import dataclass
from pathlib import Path

import yaml

from .compression import OptionalBackendUnavailable, available_backends
from .compression_config import available_modes, get_compression_config
from .language_detection import detect_language
from .debug_tools import (
    decode_for_debug,
    diff_streams,
    inspect_wrapper,
    lint_stream,
    summarise_source_map,
)
from .decoder import QYNDecoder
from .dictionary import UnknownMorphemeError
from .encoder import QYNEncoder
from .incremental import HybridDependencyResolver, IncrementalEncoder
from .package import _extract_wrapper_components, decode_package, encode_package
import qyn1.package as package_module

from .format import FrameFormatError, read_frame
from .package import decode_package, encode_package
from .migration import migrate_file
from .pipeline import encode_project
from .repository import RepositoryWriter, diff_repository_indexes, load_repository_index


class CommandError(RuntimeError):
    """Raised when a CLI sub-command fails with a user facing error."""


@dataclass
class ProgressBar:
    """Simple textual progress bar that writes to stderr."""

    total: int
    label: str
    width: int = 40
    _last_fraction: float = 0.0

    def update(self, current: int) -> None:
        if self.total <= 0:
            return
        fraction = min(max(current / self.total, 0.0), 1.0)
        if fraction - self._last_fraction < 0.02 and fraction < 1.0:
            return
        self._last_fraction = fraction
        completed = int(self.width * fraction)
        bar = "#" * completed + "-" * (self.width - completed)
        percent = int(fraction * 100)
        message = f"\r{self.label}: [{bar}] {percent:3d}%"
        print(message, file=sys.stderr, end="", flush=True)

    def complete(self) -> None:
        if self.total <= 0:
            return
        self.update(self.total)
        print(file=sys.stderr)


def _read_bytes_with_progress(path: Path, label: str, threshold: int = 256_000) -> bytes:
    size = path.stat().st_size
    if size < threshold:
        return path.read_bytes()
    progress = ProgressBar(size, label)
    progress.update(0)
    collected = bytearray()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            collected.extend(chunk)
            progress.update(len(collected))
    progress.complete()
    return bytes(collected)


def _load_passphrase(args: argparse.Namespace) -> str:
    env_secret = os.environ.get("QYN_PASSPHRASE") or os.environ.get("QUENYAN_PASSPHRASE")
    if env_secret:
        return env_secret
    keyring_service = os.environ.get("QYN_KEYRING_SERVICE")
    keyring_username = os.environ.get("QYN_KEYRING_USERNAME")
    if keyring_service and keyring_username:
        try:
            import keyring  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise CommandError(
                "Keyring lookup requested via QYN_KEYRING_SERVICE, but the 'keyring' package "
                "is not installed. Install it or unset the environment variable."
            ) from exc
        secret = keyring.get_password(keyring_service, keyring_username)
        if not secret:
            raise CommandError(
                f"Keyring secret for service '{keyring_service}' and user '{keyring_username}' not found"
            )
        return secret
    if getattr(args, "key", None):
        try:
            return Path(args.key).read_text(encoding="utf-8").strip()
        except OSError as exc:  # pragma: no cover - CLI guard
            raise CommandError(f"Unable to read key file '{args.key}': {exc}") from exc
    if getattr(args, "passphrase", None):
        return args.passphrase
    raise CommandError("A passphrase is required; provide --passphrase or --key <file>.")


def _safe_write_text(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - CLI guard
        raise CommandError(f"Failed to write to '{path}': {exc}") from exc


def _format_duration(duration: float) -> str:
    return f"{duration:.2f}s"


def encode_command(args: argparse.Namespace) -> None:
    source_path = Path(args.source)
    output_path = Path(args.output) if args.output else source_path.with_suffix(".qyn1")
    human_readable = Path(args.human_readable) if args.human_readable else None
    passphrase = _load_passphrase(args)
    source_bytes = _read_bytes_with_progress(source_path, f"Reading {source_path.name}")
    encoder = QYNEncoder(strict_morpheme_errors=args.strict_morpheme_errors)
    detection = detect_language(source_path, source_bytes, language_hint=args.language)
    profile = detection.profile
    try:
        source_text, source_encoding = profile.decode_source(source_bytes)
    except UnicodeDecodeError as exc:  # pragma: no cover - CLI guard
        raise CommandError(
            f"{source_path} could not be decoded with profile {profile.name}: {exc}"
        ) from exc
    start = time.perf_counter()
    try:
        stream = encoder.encode(
            source_text, language_profile=profile, source_encoding=source_encoding
        )
    except UnknownMorphemeError as exc:
        raise CommandError(str(exc)) from exc
    config = get_compression_config(args.compression_mode)
    backend_name = config.backend
    if args.compression_backend != "preset":
        config = config.with_backend(args.compression_backend)
        backend_name = args.compression_backend
    try:
        package = encode_package(
            stream,
            backend_name=backend_name,
            compression=config,
            model_mode=args.model_mode,
        )
    except OptionalBackendUnavailable as exc:  # pragma: no cover - CLI guard
        raise CommandError(
            f"Compression backend '{args.compression_backend}' is unavailable: {exc}"
        ) from exc
    duration = time.perf_counter() - start
    package_bytes = package.to_bytes(passphrase)
    try:
        output_path.write_bytes(package_bytes)
    except OSError as exc:  # pragma: no cover - CLI guard
        raise CommandError(f"Failed to write package '{output_path}': {exc}") from exc
    if human_readable:
        _safe_write_text(human_readable, stream.describe() + "\n")
    if not args.quiet:
        ratio = len(package_bytes) / max(len(source_bytes), 1)
        print(
            f"Encoded {source_path.name} -> {output_path.name} in {_format_duration(duration)}; "
            f"compression ratio {ratio:.2%}; language={profile.name} ({detection.reason})"
        )


def encode_project_command(args: argparse.Namespace) -> None:
    sources = [Path(item) for item in args.sources]
    passphrase = _load_passphrase(args)
    config = get_compression_config(args.compression_mode)
    backend_name = config.backend
    if args.compression_backend != "preset":
        config = config.with_backend(args.compression_backend)
        backend_name = args.compression_backend
    try:
        report = encode_project(
            sources,
            Path(args.output_dir),
            passphrase,
            backend=backend_name,
            streaming_backend=args.streaming_backend,
            streaming_threshold=args.streaming_threshold,
            chunk_size=args.chunk_size,
            max_buffered_tokens=args.max_buffered_tokens,
            max_workers=args.workers,
            compression_config=config,
            language_hint=args.language,
            strict_morpheme_errors=args.strict_morpheme_errors,
        )
    except UnknownMorphemeError as exc:
        raise CommandError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - CLI guard
        raise CommandError(f"Failed to encode project: {exc}") from exc
    summary = {
        "files": [
            {
                "source": str(result.source),
                "output": str(result.output),
                "duration_s": result.duration_s,
                "input_bytes": result.input_bytes,
                "output_bytes": result.output_bytes,
                "backend": result.backend,
                "streaming": result.streaming,
            }
            for result in report.results
        ],
        "total_duration_s": report.total_duration_s,
        "throughput_mb_s": report.average_throughput_mb_s,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Encoded {len(report.results)} files in {report.total_duration_s:.2f}s")
        print(f"Average throughput: {report.average_throughput_mb_s:.2f} MB/s")
        for result in report.results:
            print(
                f"- {result.source.name}: {result.duration_s:.2f}s, "
                f"{result.input_bytes / 1_048_576:.2f} MiB -> "
                f"{result.output_bytes / 1_048_576:.2f} MiB, backend={result.backend}"
            )


def encode_incremental_command(args: argparse.Namespace) -> None:
    sources = [Path(item).resolve() for item in args.sources]
    if not sources:
        raise CommandError("At least one source file is required for incremental encoding")
    if args.root:
        root = Path(args.root).resolve()
    else:
        common = os.path.commonpath([str(path) for path in sources])
        root = Path(common).resolve()
    config = get_compression_config(args.compression_mode)
    backend_name = args.compression_backend
    passphrase = _load_passphrase(args)
    manifest_data = {}
    if args.manifest:
        manifest_data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    resolver = HybridDependencyResolver(root, manifest_data)
    encoder = IncrementalEncoder(
        root=root,
        sources=sources,
        output_dir=Path(args.output_dir),
        cache_dir=Path(args.cache_dir),
        passphrase=passphrase,
        compression_config=config,
        backend_override=backend_name,
        dependency_resolver=resolver,
        streaming_threshold=args.streaming_threshold,
        chunk_size=args.chunk_size,
        max_buffered_tokens=args.max_buffered_tokens,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        strict_morpheme_errors=args.strict_morpheme_errors,
    )
    try:
        report = encoder.run()
    except UnknownMorphemeError as exc:
        raise CommandError(str(exc)) from exc
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print(
        f"Incremental encoding finished in {report.total_duration_s:.2f}s "
        f"with hit rate {report.hit_rate():.2%}"
    )
    print(f"Encoded: {len(report.encoded)} files, reused: {len(report.reused)}")
    if report.dependency_rebuilds:
        print(f"Dependency-triggered rebuilds: {report.dependency_rebuilds}")


def decode_command(args: argparse.Namespace) -> None:
    package_path = Path(args.package)
    output_path = Path(args.output) if args.output else package_path.with_suffix(".py")
    passphrase = _load_passphrase(args)
    package_bytes = _read_bytes_with_progress(package_path, f"Reading {package_path.name}")
    start = time.perf_counter()
    stream = decode_package(package_bytes, passphrase)
    decoder = QYNDecoder(
        stream.dictionary,
        stream.tokens,
        stream.payloads,
        payload_channels=stream.payload_channels,
    )
    module = decoder.decode()
    canonical_source = ast.unparse(module)
    _safe_write_text(output_path, canonical_source + "\n")
    if not args.quiet:
        duration = time.perf_counter() - start
        print(
            f"Decoded {package_path.name} -> {output_path.name} in {_format_duration(duration)}"
        )


def verify_command(args: argparse.Namespace) -> None:
    package_path = Path(args.package)
    raw_bytes = package_path.read_bytes()
    try:
        structured, version_obj, wrapper, _ = _extract_wrapper_components(raw_bytes)
    except Exception as exc:  # pragma: no cover - CLI guard
        if raw_bytes.startswith(package_module.WRAPPER_MAGIC):
            frame, remainder = read_frame(raw_bytes, expected_magic=package_module.WRAPPER_MAGIC)
            if remainder:
                raise ValueError("unexpected trailing data after wrapper frame")
            wrapper = json.loads(frame.body.decode("utf-8"))
            version_value = str(wrapper.get("version", frame.version.text))
        else:
            wrapper = json.loads(raw_bytes.decode("utf-8"))
            version_value = str(wrapper.get("version", "unknown"))
    except (ValueError, FrameFormatError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CommandError(f"{package_path.name} is not a valid QYN wrapper: {exc}") from exc
    metadata = wrapper.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    result = {
        "package": package_path.name,
        "version": wrapper.get("version", version_obj.text if structured else "unknown"),
        "version": version_value,
        "metadata": metadata,
    }
    needs_passphrase = bool(args.check_signature or args.key or args.passphrase)
    if needs_passphrase:
        passphrase = _load_passphrase(args)
        start = time.perf_counter()
        try:
            stream = decode_package(raw_bytes, passphrase)
        except Exception as exc:  # pragma: no cover - CLI guard
            raise CommandError(f"Failed to verify package: {exc}") from exc
        duration = time.perf_counter() - start
        result.update(
            {
                "status": "ok",
                "dictionary_version": stream.dictionary.version,
                "symbol_count": len(stream.tokens),
                "duration_s": duration,
            }
        )
        if args.check_signature:
            expected = metadata.get("source_hash")
            if expected and expected != stream.source_hash:
                raise CommandError(
                    "Authenticated metadata source hash does not match decoded payload"
                )
            result["signature_valid"] = bool(expected)
    else:
        result["status"] = "wrapper-only"
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        lines = [f"Package {result['package']} (v{result['version']})"]
        lines.append(f"Status: {result['status']}")
        if result.get("status") == "ok":
            lines.append(
                f"Dictionary {result['dictionary_version']} with {result['symbol_count']} symbols"
            )
            lines.append(f"Verified in {_format_duration(result['duration_s'])}")
            if args.check_signature:
                if result.get("signature_valid"):
                    lines.append("Source hash matches authenticated metadata")
                else:
                    lines.append("No authenticated source hash present")
        elif metadata:
            lines.append("Wrapper metadata available; provide --key to verify contents")
        print("\n".join(lines))


def compression_backends_command(args: argparse.Namespace) -> None:
    statuses = available_backends()
    if args.json:
        print(json.dumps(statuses, indent=2))
    else:
        for name, status in statuses.items():
            print(f"{name}: {status}")


def inspect_command(args: argparse.Namespace) -> None:
    report = inspect_wrapper(Path(args.package), validate_audit=args.validate_audit)
    payload = report.to_dict()
    if not args.show_metadata:
        payload.pop("metadata", None)
    if args.yaml:
        print(yaml.safe_dump(payload, sort_keys=False))
        return
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    print(f"Package: {args.package}")
    print(f"Version: {report.version}")
    print(f"Size: {report.size_bytes} bytes")
    if report.signature_valid is not None:
        if report.signature_valid:
            print("Integrity signature: OK")
        else:
            print("Integrity signature: INVALID")
    if report.provenance:
        print("Provenance:")
        for key, value in sorted(report.provenance.items()):
            print(f"  {key}: {value}")
    if args.show_metadata and report.metadata:
        print("Metadata:")
        for key, value in sorted(report.metadata.items()):
            print(f"  {key}: {value}")
    elif not args.show_metadata and report.metadata:
        print("Metadata hidden; pass --show-metadata to display fields")
    if args.validate_audit:
        if report.audit_issues:
            print("Audit trail issues detected:")
            for issue in report.audit_issues:
                print(f"  - {issue}")
        else:
            print("Audit trail: OK")


def source_map_command(args: argparse.Namespace) -> None:
    passphrase = _load_passphrase(args)
    stream = decode_for_debug(Path(args.package), passphrase)
    if stream.source_map is None:
        raise SystemExit("Package does not include a source map")
    if args.output:
        stream.source_map.write(args.output)
    summary = summarise_source_map(stream)
    if args.json:
        print(json.dumps(summary, indent=2))
    elif not args.output:
        for key, value in summary.items():
            print(f"{key}: {value}")


def decompile_command(args: argparse.Namespace) -> None:
    passphrase = _load_passphrase(args)
    package_bytes = Path(args.package).read_bytes()
    stream = decode_package(package_bytes, passphrase)
    decoder = QYNDecoder(
        stream.dictionary,
        stream.tokens,
        stream.payloads,
        payload_channels=stream.payload_channels,
    )
    module = decoder.decode()
    canonical_source = ast.unparse(module)
    if args.output:
        Path(args.output).write_text(canonical_source + "\n", encoding="utf-8")
    else:
        print(canonical_source)


def diff_command(args: argparse.Namespace) -> None:
    passphrase = _load_passphrase(args)
    stream_a = decode_for_debug(Path(args.package_a), passphrase)
    stream_b = decode_for_debug(Path(args.package_b), passphrase)
    diff = diff_streams(stream_a, stream_b)
    print(json.dumps(diff, indent=2))


def lint_command(args: argparse.Namespace) -> None:
    passphrase = _load_passphrase(args)
    stream = decode_for_debug(Path(args.package), passphrase)
    issues = lint_stream(stream)
    if issues:
        for issue in issues:
            print(f"WARNING: {issue}")
        raise SystemExit(1)
    print("OK: no lint issues found")


def morphemes_command(args: argparse.Namespace) -> None:
    passphrase = _load_passphrase(args)
    stream = decode_for_debug(Path(args.package), passphrase)
    output = "\n".join(stream.human_readable)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


def migrate_command(args: argparse.Namespace) -> None:
    package_path = Path(args.package)
    output_path = Path(args.output) if args.output else package_path
    passphrase = _load_passphrase(args)
    if not package_path.exists():
        raise CommandError(f"Input package '{package_path}' does not exist")
    raw_bytes = package_path.read_bytes()
    backup_path: Path | None = None
    if output_path == package_path and not args.no_backup:
        backup_path = package_path.with_suffix(package_path.suffix + ".bak")
        backup_path.write_bytes(raw_bytes)
    if output_path != package_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = migrate_file(
            package_path,
            output_path,
            passphrase,
            target_dictionary=args.target_dictionary,
            target_package_version=args.target_package,
            strict_morpheme_errors=args.strict_morpheme_errors,
        )
    except UnknownMorphemeError as exc:
        raise CommandError(str(exc)) from exc
    except ValueError as exc:
        raise CommandError(f"Migration failed: {exc}") from exc
    if args.quiet:
        return
    summary = (
        f"Migrated {package_path.name} -> {output_path.name} "
        f"(dictionary {report.dictionary_version}, format {report.package_version})"
    )
    if report.missing_keys:
        summary += "; remapped " + ", ".join(report.missing_keys)
    print(summary)
    if backup_path is not None:
        print(f"Backup written to {backup_path}")


def repo_pack_command(args: argparse.Namespace) -> None:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    root = Path(args.root or manifest.get("root", ".")).resolve()
    base = Path(args.manifest).resolve().parent
    compression_mode = args.compression_mode or manifest.get("compression_mode", "balanced")
    backend = args.backend or manifest.get("backend", "rans")
    writer = RepositoryWriter(
        root,
        Path(args.output),
        compression_mode=compression_mode,
        backend=backend,
    )
    for entry in manifest.get("entries", []):
        source = root / entry["source"]
        package_path = (base / entry["package"]).resolve()
        metadata = entry.get("metadata", {})
        writer.add_package(source, package_path.read_bytes(), metadata=metadata)
    index = writer.finalise()
    if args.archive:
        writer.build_monolithic_archive(Path(args.archive))
    payload = index.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"Repository created at {args.output} with {len(index.entries)} entries "
            f"(mode={index.compression_mode}, backend={index.backend})"
        )


def repo_diff_command(args: argparse.Namespace) -> None:
    current = load_repository_index(Path(args.current))
    previous = load_repository_index(Path(args.previous))
    diff = diff_repository_indexes(current, previous)
    if args.json:
        print(json.dumps(diff, indent=2))
        return
    print("Changes since previous repository index:")
    for key in ("added", "removed", "changed"):
        values = diff.get(key, [])
        print(f"{key}: {len(values)}")
        for value in values:
            print(f"  - {value}")


def init_command(args: argparse.Namespace) -> None:
    target = Path(args.directory or ".").resolve()
    config_dir = target / ".quenyan"
    keys_dir = config_dir / "keys"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "default_compression_mode": args.compression_mode,
        "default_backend": args.compression_backend,
        "cache_dir": str((config_dir / "cache").resolve()),
    }
    _safe_write_text(config_dir / "config.json", json.dumps(config, indent=2) + "\n")
    created_key = None
    if args.generate_keys:
        keys_dir.mkdir(exist_ok=True)
        master_key_path = keys_dir / "master.key"
        if not master_key_path.exists() or args.force:
            secret = secrets.token_urlsafe(32)
            _safe_write_text(master_key_path, secret + "\n")
            created_key = master_key_path
        else:
            created_key = master_key_path
    if not args.quiet:
        print(f"Initialised Quenyan workspace at {config_dir}")
        if created_key:
            print(f"Generated master key at {created_key}")


_COMMANDS = [
    "encode",
    "decode",
    "verify",
    "inspect",
    "diff",
    "init",
    "completion",
    "man",
    "compression-backends",
    "encode-project",
    "encode-incremental",
    "source-map",
    "decompile",
    "lint",
    "morphemes",
    "repo-pack",
    "repo-diff",
]


def completion_command(args: argparse.Namespace) -> None:
    scripts = {
        "bash": textwrap.dedent(
            f"""
            _quenyan_complete() {{
                local cur prev opts
                COMPREPLY=()
                cur="${{COMP_WORDS[COMP_CWORD]}}"
                prev="${{COMP_WORDS[COMP_CWORD-1]}}"
                opts="{' '.join(_COMMANDS)}"
                if [[ $COMP_CWORD -eq 1 ]]; then
                    COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
                    return 0
                fi
                case "${{COMP_WORDS[1]}}" in
                    encode|decode)
                        COMPREPLY=( $(compgen -f -- "$cur") )
                        ;;
                    diff)
                        COMPREPLY=( $(compgen -f -- "$cur") )
                        ;;
                    *)
                        COMPREPLY=( $(compgen -f -- "$cur") )
                        ;;
                esac
                return 0
            }}
            complete -F _quenyan_complete quenyan
            """
        ).strip(),
        "zsh": textwrap.dedent(
            f"""
            #compdef quenyan
            _arguments '1: :({ ' '.join(_COMMANDS) })' '*::filename:_files'
            """
        ).strip(),
        "fish": textwrap.dedent(
            f"""
            complete -c quenyan -f
            complete -c quenyan -n 'not __fish_seen_subcommand_from {" ".join(_COMMANDS)}' -a "{' '.join(_COMMANDS)}"
            complete -c quenyan -n '__fish_seen_subcommand_from encode decode diff' -a '(commandline -ct)'
            """
        ).strip(),
    }
    script = scripts.get(args.shell)
    if script is None:
        raise CommandError(f"Unsupported shell '{args.shell}'. Choose from bash, zsh, fish.")
    print(script)


def man_command(args: argparse.Namespace) -> None:
    manual_path = Path(__file__).resolve().parent.parent / "docs" / "man" / "quenyan.1.md"
    if not manual_path.exists():
        raise CommandError("Manual page not found in docs/man/quenyan.1.md")
    print(manual_path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    encode_parser = subparsers.add_parser("encode", help="Encode Python source")
    encode_parser.add_argument("source", help="Input source file")
    encode_parser.add_argument("-o", "--output", help="Destination QYN package (default: <source>.qyn1)")
    encode_parser.add_argument("--key", help="Path to file containing encryption passphrase")
    encode_parser.add_argument("--passphrase", help="Encryption passphrase (discouraged for CI)")
    encode_parser.add_argument("--human-readable", help="Optional file to write human-readable morpheme stream")
    encode_parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    encode_parser.add_argument(
        "--strict-morpheme-errors",
        action="store_true",
        help="Fail if the encoder encounters an unknown morpheme key",
    )
    encode_parser.add_argument(
        "--language",
        help="Explicit language profile name or manifest path (default: auto-detect)",
    )
    backend_choices = sorted(available_backends().keys())
    encode_parser.add_argument(
        "--compression-backend",
        default="preset",
        choices=["preset", *backend_choices],
        help="Override backend (default: preset from compression mode)",
    )
    encode_parser.add_argument(
        "--compression-mode",
        default="balanced",
        choices=sorted(available_modes().keys()),
        help="Preset controlling multi-stage compression optimisations (default: balanced)",
    )
    encode_parser.add_argument(
        "--model-mode",
        default="adaptive",
        choices=["adaptive", "static", "hybrid"],
        help="Select model behaviour for morpheme streams",
    )
    encode_parser.set_defaults(func=encode_command)

    project_parser = subparsers.add_parser(
        "encode-project", help="Encode multiple source files in parallel",
    )
    project_parser.add_argument("output_dir", help="Directory to write packages")
    project_parser.add_argument(
        "sources",
        nargs="+",
        help="Source files to encode",
    )
    project_parser.add_argument(
        "--language",
        help="Explicit language profile for all sources (default: auto-detect per file)",
    )
    project_parser.add_argument(
        "--strict-morpheme-errors",
        action="store_true",
        help="Fail if the encoder encounters an unknown morpheme key",
    )
    project_parser.add_argument("--key", help="Path to passphrase file")
    project_parser.add_argument("--passphrase", help="Encryption passphrase")
    project_parser.add_argument(
        "--compression-backend",
        default="preset",
        choices=["preset", *backend_choices],
        help="Backend override for non-streaming files (default: preset)",
    )
    project_parser.add_argument(
        "--compression-mode",
        default="balanced",
        choices=sorted(available_modes().keys()),
        help="Compression preset (balanced, maximum, security)",
    )
    project_parser.add_argument(
        "--streaming-backend",
        default="chunked-rans",
        choices=sorted(available_backends().keys()),
        help="Backend to use for streaming encodes (default: chunked-rans)",
    )
    project_parser.add_argument(
        "--streaming-threshold",
        type=int,
        default=32 * 1024 * 1024,
        help="Switch to streaming mode for files >= this many bytes",
    )
    project_parser.add_argument(
        "--chunk-size",
        type=int,
        default=65536,
        help="Number of tokens per chunk for streaming compression",
    )
    project_parser.add_argument(
        "--max-buffered-tokens",
        type=int,
        default=65536,
        help="Maximum tokens to buffer in memory per stream chunk",
    )
    project_parser.add_argument(
        "--workers",
        type=int,
        help="Number of worker processes (default: CPU count)",
    )
    project_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON summary",
    )
    project_parser.set_defaults(func=encode_project_command)

    incremental_parser = subparsers.add_parser(
        "encode-incremental", help="Incrementally encode a project with caching",
    )
    incremental_parser.add_argument("output_dir", help="Directory for encoded packages")
    incremental_parser.add_argument(
        "sources",
        nargs="+",
        help="Source files to encode incrementally",
    )
    incremental_parser.add_argument(
        "--key",
        help="Path to passphrase file",
    )
    incremental_parser.add_argument(
        "--passphrase",
        help="Encryption passphrase",
    )
    incremental_parser.add_argument(
        "--cache-dir",
        required=True,
        help="Directory to persist incremental cache entries",
    )
    incremental_parser.add_argument(
        "--root",
        help="Project root (defaults to the common ancestor of sources)",
    )
    incremental_parser.add_argument(
        "--manifest",
        help="JSON manifest describing explicit dependencies",
    )
    incremental_parser.add_argument(
        "--strict-morpheme-errors",
        action="store_true",
        help="Fail if the encoder encounters an unknown morpheme key",
    )
    incremental_parser.add_argument(
        "--compression-backend",
        default="preset",
        choices=["preset", *backend_choices],
        help="Override compression backend (default: preset)",
    )
    incremental_parser.add_argument(
        "--compression-mode",
        default="balanced",
        choices=sorted(available_modes().keys()),
        help="Compression preset to apply",
    )
    incremental_parser.add_argument(
        "--streaming-threshold",
        type=int,
        default=32 * 1024 * 1024,
        help="Enable streaming encoder for files >= this many bytes",
    )
    incremental_parser.add_argument(
        "--chunk-size",
        type=int,
        default=65536,
        help="Tokens per chunk when streaming",
    )
    incremental_parser.add_argument(
        "--max-buffered-tokens",
        type=int,
        default=65536,
        help="Maximum buffered tokens per streaming chunk",
    )
    incremental_parser.add_argument("--shard-index", type=int, default=0, help="Current CI shard index")
    incremental_parser.add_argument(
        "--shard-count", type=int, default=1, help="Total number of CI shards running in parallel"
    )
    incremental_parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    incremental_parser.set_defaults(func=encode_incremental_command)

    decode_parser = subparsers.add_parser("decode", help="Decode a QYN-1 package")
    decode_parser.add_argument("package", help="Input QYN package")
    decode_parser.add_argument("-o", "--output", help="Output source file (default: <package>.py)")
    decode_parser.add_argument("--key", help="Path to passphrase file")
    decode_parser.add_argument("--passphrase", help="Decryption passphrase")
    decode_parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    decode_parser.set_defaults(func=decode_command)

    verify_parser = subparsers.add_parser("verify", help="Verify package integrity")
    verify_parser.add_argument("package", help="Input QYN package")
    verify_parser.add_argument("--key", help="Path to passphrase file")
    verify_parser.add_argument("--passphrase", help="Passphrase for verification")
    verify_parser.add_argument("--check-signature", action="store_true", help="Validate source hash matches payload")
    verify_parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    verify_parser.set_defaults(func=verify_command)

    backends_parser = subparsers.add_parser(
        "compression-backends", help="List available compression backends"
    )
    backends_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human readable text",
    )
    backends_parser.set_defaults(func=compression_backends_command)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect wrapper metadata")
    inspect_parser.add_argument("package", help="Input QYN package")
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON")
    inspect_parser.add_argument("--yaml", action="store_true", help="Emit YAML")
    inspect_parser.add_argument("--show-metadata", action="store_true", help="Include wrapper metadata in output")
    inspect_parser.add_argument(
        "--validate-audit",
        action="store_true",
        help="Validate audit trail chronology",
    )
    inspect_parser.set_defaults(func=inspect_command)

    source_map_parser = subparsers.add_parser(
        "source-map", help="Summarise or export the embedded source map"
    )
    source_map_parser.add_argument("package", help="Input QYN-1 package")
    source_map_parser.add_argument("--key", help="Path to passphrase file")
    source_map_parser.add_argument("--passphrase", help="Decryption passphrase")
    source_map_parser.add_argument("--output", help="Optional destination file for the source map")
    source_map_parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    source_map_parser.set_defaults(func=source_map_command)

    decompile_parser = subparsers.add_parser("decompile", help="Emit canonical source")
    decompile_parser.add_argument("package", help="Input QYN-1 package")
    decompile_parser.add_argument("--key", help="Path to passphrase file")
    decompile_parser.add_argument("--passphrase", help="Decryption passphrase")
    decompile_parser.add_argument("--output", help="Optional destination file")
    decompile_parser.set_defaults(func=decompile_command)

    diff_parser = subparsers.add_parser(
        "diff", help="Compare two packages at the morpheme level"
    )
    diff_parser.add_argument("package_a", help="First package")
    diff_parser.add_argument("package_b", help="Second package")
    diff_parser.add_argument("--key", help="Path to passphrase file")
    diff_parser.add_argument("--passphrase", help="Decryption passphrase")
    diff_parser.set_defaults(func=diff_command)

    lint_parser = subparsers.add_parser("lint", help="Run static analysis on a package")
    lint_parser.add_argument("package", help="Input QYN-1 package")
    lint_parser.add_argument("--key", help="Path to passphrase file")
    lint_parser.add_argument("--passphrase", help="Decryption passphrase")
    lint_parser.set_defaults(func=lint_command)

    morphemes_parser = subparsers.add_parser(
        "morphemes", help="Print the human readable morpheme stream"
    )
    morphemes_parser.add_argument("package", help="Input QYN-1 package")
    morphemes_parser.add_argument("--key", help="Path to passphrase file")
    morphemes_parser.add_argument("--passphrase", help="Decryption passphrase")
    morphemes_parser.add_argument("--output", help="Optional destination file")
    morphemes_parser.set_defaults(func=morphemes_command)

    migrate_parser = subparsers.add_parser(
        "migrate", help="Upgrade or remap an MCS package to a new version"
    )
    migrate_parser.add_argument("package", help="Input QYN-1 package")
    migrate_parser.add_argument("--output", help="Destination package (default: overwrite input)")
    migrate_parser.add_argument(
        "--target-dictionary",
        help="Dictionary version to migrate to (default: preserve existing)",
    )
    migrate_parser.add_argument(
        "--target-package",
        help="Target package format version (default: current)",
    )
    migrate_parser.add_argument(
        "--strict-morpheme-errors",
        action="store_true",
        help="Fail if the target dictionary cannot represent existing morphemes",
    )
    migrate_parser.add_argument("--key", help="Path to passphrase file")
    migrate_parser.add_argument("--passphrase", help="Passphrase for decrypting and re-encrypting")
    migrate_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip writing a .bak file when overwriting the input",
    )
    migrate_parser.add_argument("--quiet", action="store_true", help="Suppress status output")
    migrate_parser.set_defaults(func=migrate_command)

    repo_pack_parser = subparsers.add_parser(
        "repo-pack", help="Build a repository archive from encoded packages"
    )
    repo_pack_parser.add_argument("manifest", help="JSON manifest describing packages to include")
    repo_pack_parser.add_argument("output", help="Directory to write repository artefacts")
    repo_pack_parser.add_argument("--root", help="Override project root declared in manifest")
    repo_pack_parser.add_argument("--compression-mode", help="Compression mode label to record")
    repo_pack_parser.add_argument("--backend", help="Compression backend label to record")
    repo_pack_parser.add_argument("--archive", help="Optional monolithic archive destination")
    repo_pack_parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    repo_pack_parser.set_defaults(func=repo_pack_command)

    repo_diff_parser = subparsers.add_parser(
        "repo-diff", help="Compare two repository indexes"
    )
    repo_diff_parser.add_argument("current", help="Current repository index.json")
    repo_diff_parser.add_argument("previous", help="Previous repository index.json")
    repo_diff_parser.add_argument("--json", action="store_true", help="Emit JSON diff")
    repo_diff_parser.set_defaults(func=repo_diff_command)

    init_parser = subparsers.add_parser("init", help="Initialise a project for Quenyan")
    init_parser.add_argument("directory", nargs="?", help="Project root (default: current directory)")
    init_parser.add_argument("--generate-keys", action="store_true", help="Create a new master key")
    init_parser.add_argument("--compression-mode", default="balanced", choices=sorted(available_modes().keys()), help="Default compression mode to store in config")
    init_parser.add_argument(
        "--compression-backend",
        default="rans",
        choices=sorted(available_backends().keys()),
        help="Default backend to store in config",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing keys")
    init_parser.add_argument("--quiet", action="store_true", help="Suppress output")
    init_parser.set_defaults(func=init_command)

    completion_parser = subparsers.add_parser("completion", help="Emit shell completion script")
    completion_parser.add_argument("shell", choices=["bash", "zsh", "fish"], help="Shell to generate completions for")
    completion_parser.set_defaults(func=completion_command)

    man_parser = subparsers.add_parser("man", help="Display the CLI manual page")
    man_parser.set_defaults(func=man_command)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except CommandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
