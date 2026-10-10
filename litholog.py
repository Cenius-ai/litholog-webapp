#!/usr/bin/env python3
"""LithoLog - rock layer description logger, stratigraphic column builder and
fossil find register.

LithoLog is a single-file command-line tool for field geologists working
offline in one directory. Everything it knows lives in ./litholog.json, a
pretty-printed, hand-editable file that is rewritten atomically so an
interrupted write can never destroy the last good section.

Commands
    litholog layer add --lithology <keyword> --thickness <m> [--description <text>]
    litholog layer list
    litholog column
    litholog fossil add --taxon <name> --depth <m>
    litholog fossil list
    litholog operator set --name "<name>"
    litholog whoami

Design tokens (committed direction: calm-precise, mono, compact, terminal dark).
The palette below is the product's single accent plus its neutral ramp, and the
accent paints primary status lines only. Output stays plain ASCII unless
`--color=always` is asked for, so transcripts diff byte for byte and no status is
ever signalled by colour alone.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

STORE_FILENAME = "litholog.json"
SCHEMA_VERSION = 1

# One glyph per known lithology so every drawn row is visually different.
LITHOLOGY_PATTERNS: dict[str, str] = {
    "shale": "=",
    "sandstone": ".",
    "limestone": "#",
    "mudstone": "-",
    "siltstone": ":",
    "conglomerate": "o",
    "coal": "@",
}
LITHOLOGY_KEYWORDS: tuple[str, ...] = tuple(LITHOLOGY_PATTERNS)
BED_HEIGHT_M = 0.5

LAYER_EMPTY_HINT = (
    "No layers recorded yet. Add one with: litholog layer add --lithology shale --thickness 1.0"
)
FOSSIL_EMPTY_HINT = (
    "No fossils recorded yet. Add one with: litholog fossil add --taxon Ammonite --depth 1.2"
)
OPERATOR_EMPTY_HINT = 'No operator set. Set one with: litholog operator set --name "Jane Doe"'

#: Committed design tokens: accent oklch(0.58 0.12 43) == #b4603c, neutral ramp
#: on a terminal-dark surface. Used by the opt-in colour path only.
THEME: dict[str, str] = {
    "accent": "#b4603c",
    "accent_ansi256": "131",
    "surface": "#14110f",
    "text": "#e8e2dd",
    "muted": "#a89f98",
    "rule": "#3a332e",
}


class Printer:
    """Write result lines to stdout.

    `status()` marks a primary status line (an add confirmation, a count line,
    the column header) so the accent can paint it when `--color=always` was
    asked for. Status text always reads correctly without colour.
    """

    def __init__(self, use_color: bool) -> None:
        self.use_color = use_color

    def __call__(self, text: str) -> None:
        print(text)

    def status(self, text: str) -> None:
        if self.use_color:
            print(f"\x1b[38;5;{THEME['accent_ansi256']}m{text}\x1b[0m")
        else:
            print(text)


class StoreError(Exception):
    """Raised when ./litholog.json cannot be read or written.

    Every StoreError becomes exactly one 'Error: ...' line on stderr plus exit
    status 1 - never a traceback.
    """


# --------------------------------------------------------------------------- #
# store: read, validate, atomic write
# --------------------------------------------------------------------------- #


def empty_store() -> dict[str, Any]:
    """Return a fresh in-memory store (never written to disk on its own)."""
    return {"version": SCHEMA_VERSION, "operator": None, "layers": [], "fossils": []}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_store(data: Any) -> None:
    """Reject anything that is not a well-formed store.

    A hand-edited file that does not match the documented shape is refused
    rather than silently repaired, so a typo can never cost the operator the
    rest of the section.
    """
    if not isinstance(data, dict):
        raise StoreError(f"cannot read {STORE_FILENAME}")
    version = data.get("version", SCHEMA_VERSION)
    if not isinstance(version, int) or isinstance(version, bool):
        raise StoreError(f"cannot read {STORE_FILENAME}")
    operator = data.get("operator")
    if operator is not None and not isinstance(operator, str):
        raise StoreError(f"cannot read {STORE_FILENAME}")
    for layer in data.get("layers", []):
        if not isinstance(layer, dict):
            raise StoreError(f"cannot read {STORE_FILENAME}")
        if not isinstance(layer.get("id"), str):
            raise StoreError(f"cannot read {STORE_FILENAME}")
        if layer.get("lithology") not in LITHOLOGY_PATTERNS:
            raise StoreError(f"cannot read {STORE_FILENAME}")
        thickness = layer.get("thickness_m")
        if not _is_number(thickness) or float(thickness) <= 0:
            raise StoreError(f"cannot read {STORE_FILENAME}")
        if not isinstance(layer.get("description", ""), str):
            raise StoreError(f"cannot read {STORE_FILENAME}")
    for fossil in data.get("fossils", []):
        if not isinstance(fossil, dict):
            raise StoreError(f"cannot read {STORE_FILENAME}")
        if not isinstance(fossil.get("id"), str):
            raise StoreError(f"cannot read {STORE_FILENAME}")
        if not isinstance(fossil.get("taxon"), str):
            raise StoreError(f"cannot read {STORE_FILENAME}")
        depth = fossil.get("depth_m")
        if not _is_number(depth) or float(depth) < 0:
            raise StoreError(f"cannot read {STORE_FILENAME}")


def load_store() -> dict[str, Any]:
    """Read ./litholog.json.

    A missing file is not an error - it is simply an empty section, and it is
    left absent so `layer list` on a fresh directory creates nothing.
    """
    if not os.path.exists(STORE_FILENAME):
        return empty_store()
    try:
        with open(STORE_FILENAME, "r", encoding="utf-8") as handle:
            text = handle.read()
        # Strict JSON text parsing only - no dynamic code evaluation and no
        # binary formats - so a store can never execute anything on the machine
        # that reads it, and a failed parse is simply an unreadable store.
        data = json.loads(text)
    except (OSError, ValueError, RecursionError) as exc:
        raise StoreError(f"cannot read {STORE_FILENAME}") from exc
    _validate_store(data)
    return data


def _default_file_mode() -> int:
    """Permission bits a normal file would get under the current umask."""
    current_umask = os.umask(0)
    os.umask(current_umask)
    return 0o666 & ~current_umask


def save_store(data: dict[str, Any]) -> None:
    """Write the store atomically: temp file in the same directory, then replace."""
    data["version"] = SCHEMA_VERSION
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    directory = os.path.dirname(os.path.abspath(STORE_FILENAME)) or "."
    handle_fd, temp_path = tempfile.mkstemp(prefix=".litholog-", suffix=".tmp", dir=directory)
    # mkstemp creates 0600; a hand-editable store should look like any other file.
    os.chmod(temp_path, _default_file_mode())
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, STORE_FILENAME)
    except OSError as exc:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise StoreError(f"cannot write {STORE_FILENAME}") from exc


def _layers(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data.setdefault("layers", [])


def _fossils(data: dict[str, Any]) -> list[dict[str, Any]]:
    return data.setdefault("fossils", [])


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #


def format_metres(value: float) -> str:
    """Format a depth/thickness with at least one decimal and no trailing zeros."""
    text = f"{float(value):.3f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def _printable(text: str) -> str:
    """Collapse control characters so one record can never break the table."""
    return "".join(
        " " if character < " " or character == "\x7f" else character for character in text
    )


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render left-aligned columns with two-space gutters."""
    widths = [
        max([len(headers[index])] + [len(row[index]) for row in rows])
        for index in range(len(headers))
    ]
    lines = [_layout_row(headers, widths)]
    lines.append(_layout_row(["-" * width for width in widths], widths))
    lines.extend(_layout_row(row, widths) for row in rows)
    return "\n".join(line.rstrip() for line in lines)


def _layout_row(cells: Sequence[str], widths: Sequence[int]) -> str:
    padded = [cell.ljust(widths[index]) for index, cell in enumerate(cells)]
    return "  ".join(padded)


# --------------------------------------------------------------------------- #
# flag validation: every failure is one product-language line plus exit 1
# --------------------------------------------------------------------------- #


def _required(value: str | None, flag: str) -> str:
    if value is None or not value.strip():
        raise UsageError(f"{flag} is required")
    return value.strip()


def _positive_metres(value: str | None, flag: str) -> float:
    if value is None:
        raise UsageError(f"{flag} is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise UsageError(f"{flag} must be a number") from None
    if math.isnan(number) or math.isinf(number):
        raise UsageError(f"{flag} must be a number")
    if number <= 0:
        raise UsageError(f"{flag} must be greater than 0")
    return number


def _operator_name(value: str | None) -> str:
    if value is None:
        raise UsageError("--name is required")
    if not value.strip():
        raise UsageError("--name must not be empty")
    return value.strip()


def _non_negative_metres(value: str | None, flag: str) -> float:
    if value is None:
        raise UsageError(f"{flag} is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise UsageError(f"{flag} must be a number") from None
    if math.isnan(number) or math.isinf(number):
        raise UsageError(f"{flag} must be a number")
    if number < 0:
        raise UsageError(f"{flag} must not be negative")
    return number


class UsageError(Exception):
    """A rejected flag - printed as 'Error: <message>' with exit status 1."""


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


def command_layer_add(args: argparse.Namespace, out: Printer) -> int:
    lithology = _required(args.lithology, "--lithology")
    if lithology not in LITHOLOGY_PATTERNS:
        raise UsageError("--lithology must be one of " + ", ".join(LITHOLOGY_KEYWORDS))
    thickness = _positive_metres(args.thickness, "--thickness")
    # An omitted description stores an empty string; a given one is stored verbatim.
    description = args.description if args.description is not None else ""

    data = load_store()
    layers = _layers(data)
    layer = {
        "id": f"L{len(layers) + 1}",
        "lithology": lithology,
        "thickness_m": thickness,
        "description": description,
    }
    layers.append(layer)
    save_store(data)
    out.status(f"Added layer {layer['id']} ({layer['lithology']}, {format_metres(thickness)} m)")
    return 0


def command_layer_list(args: argparse.Namespace, out: Printer) -> int:
    layers = _layers(load_store())
    if not layers:
        out(LAYER_EMPTY_HINT)
        return 0
    rows = [
        [
            layer["id"],
            layer["lithology"],
            f"{format_metres(layer['thickness_m'])} m",
            _printable(layer.get("description", "")) or "-",
        ]
        for layer in layers
    ]
    out(render_table(["ID", "LITHOLOGY", "THICKNESS", "DESCRIPTION"], rows))
    out.status(f"Layers: {len(layers)}")
    return 0


def command_column(args: argparse.Namespace, out: Printer) -> int:
    layers = _layers(load_store())
    if not layers:
        out(LAYER_EMPTY_HINT)
        return 0
    total = sum(float(layer["thickness_m"]) for layer in layers)
    out.status(f"Stratigraphic column - {len(layers)} layers, total {format_metres(total)} m")
    rows: list[list[str]] = []
    depth = 0.0
    for layer in layers:
        rows.extend(_column_rows(layer, depth))
        depth = round(depth + float(layer["thickness_m"]), 10)
    widths = [max(len(row[index]) for row in rows) for index in range(4)]
    for row in rows:
        out("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip())
    return 0


def _column_rows(layer: dict[str, Any], top_depth: float) -> list[list[str]]:
    """One row per 0.5 m band, rounded up, with a minimum of one visible row."""
    thickness = float(layer["thickness_m"])
    bands = max(1, int(-(-thickness // BED_HEIGHT_M)))
    pattern = LITHOLOGY_PATTERNS[layer["lithology"]]
    bar = pattern * max(1, bands)
    bottom_depth = round(top_depth + thickness, 10)
    rows: list[list[str]] = []
    for band in range(bands):
        band_top = round(top_depth + band * BED_HEIGHT_M, 10)
        band_bottom = min(round(band_top + BED_HEIGHT_M, 10), bottom_depth)
        rows.append(
            [
                f"{format_metres(band_top)}-{format_metres(band_bottom)} m",
                bar,
                layer["lithology"],
                f"{format_metres(thickness)} m",
            ]
        )
    return rows


def command_fossil_add(args: argparse.Namespace, out: Printer) -> int:
    taxon = _required(args.taxon, "--taxon")
    depth = _non_negative_metres(args.depth, "--depth")

    data = load_store()
    fossils = _fossils(data)
    fossil = {"id": f"F{len(fossils) + 1}", "taxon": taxon, "depth_m": depth}
    fossils.append(fossil)
    save_store(data)
    out.status(f"Added fossil {fossil['id']} ({taxon} at {format_metres(depth)} m)")
    return 0


def command_fossil_list(args: argparse.Namespace, out: Printer) -> int:
    fossils = _fossils(load_store())
    if not fossils:
        out(FOSSIL_EMPTY_HINT)
        return 0
    ordered = sorted(fossils, key=lambda fossil: float(fossil["depth_m"]))
    rows = [
        [fossil["id"], _printable(fossil["taxon"]), f"{format_metres(fossil['depth_m'])} m"]
        for fossil in ordered
    ]
    out(render_table(["ID", "TAXON", "DEPTH"], rows))
    out.status(f"Fossils: {len(fossils)}")
    return 0


def command_operator_set(args: argparse.Namespace, out: Printer) -> int:
    name = _operator_name(args.name)
    data = load_store()
    data["operator"] = name
    save_store(data)
    out.status(f"Operator set to {name}")
    return 0


def command_whoami(args: argparse.Namespace, out: Printer) -> int:
    operator = load_store().get("operator")
    out.status(f"Operator: {operator}" if operator else OPERATOR_EMPTY_HINT)
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #

DESCRIPTION = "Log rock layers, draw a stratigraphic column and register fossil finds."

EXAMPLES = """\
examples:
  litholog layer add --lithology shale --thickness 1.2 --description "fissile dark shale"
  litholog layer add --lithology sandstone --thickness 3.8
  litholog layer list
  litholog column
  litholog fossil add --taxon Ammonite --depth 4.5
  litholog fossil list
  litholog operator set --name "Jane Doe"
  litholog whoami

lithology keywords and their column patterns:
  shale =   sandstone .   limestone #   mudstone -
  siltstone :   conglomerate o   coal @

state lives in ./litholog.json in the current directory; every command is
non-interactive and plain ASCII, and errors are a single 'Error: ...' line.
"""


class LithologArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that answers a usage error with the full help text.

    The product contract is a usage summary and no traceback, so a mistyped
    command lists every command instead of failing with one cryptic line.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_help(sys.stderr)
        print(f"Error: {message}", file=sys.stderr)
        self.exit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = LithologArgumentParser(
        prog="litholog",
        description=DESCRIPTION,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version="litholog 1.0")
    parser.add_argument(
        "--color",
        choices=("never", "always"),
        default="never",
        help=(
            "paint primary status lines with the accent; default 'never' keeps "
            "every transcript plain ASCII"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    layer = subparsers.add_parser(
        "layer",
        help="record and list described rock layers",
        description="Record and list described rock layers.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    layer_actions = layer.add_subparsers(dest="action", metavar="<action>")

    layer_add = layer_actions.add_parser(
        "add",
        help="append a described layer",
        description="Append a described layer to ./litholog.json.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    layer_add.add_argument(
        "--lithology", metavar="<keyword>", help="one of " + ", ".join(LITHOLOGY_KEYWORDS)
    )
    layer_add.add_argument(
        "--thickness", metavar="<m>", help="bed thickness in metres, greater than 0"
    )
    layer_add.add_argument(
        "--description", metavar="<text>", help="free-text description, stored verbatim"
    )
    layer_add.set_defaults(handler=command_layer_add)

    layer_list = layer_actions.add_parser(
        "list",
        help="list recorded layers in insertion order",
        description="List recorded layers in insertion order, oldest flag first.",
    )
    layer_list.set_defaults(handler=command_layer_list)

    column = subparsers.add_parser(
        "column",
        help="draw the recorded layers as a text stratigraphic column",
        description="Draw the recorded layers top-down as a text stratigraphic column.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    column.set_defaults(handler=command_column)

    fossil = subparsers.add_parser(
        "fossil",
        help="register and list fossil finds",
        description="Register and list fossil finds.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fossil_actions = fossil.add_subparsers(dest="action", metavar="<action>")

    fossil_add = fossil_actions.add_parser(
        "add",
        help="append a fossil find at a measured depth",
        description="Append a fossil find at a measured depth.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    fossil_add.add_argument("--taxon", metavar="<name>", help="fossil name, required and non-empty")
    fossil_add.add_argument("--depth", metavar="<m>", help="depth in metres, zero or greater")
    fossil_add.set_defaults(handler=command_fossil_add)

    fossil_list = fossil_actions.add_parser(
        "list",
        help="list fossil finds sorted by depth",
        description="List fossil finds sorted by measured depth, shallowest first.",
    )
    fossil_list.set_defaults(handler=command_fossil_list)

    operator = subparsers.add_parser(
        "operator",
        help="label the store with the local operator name",
        description="Label this store with the name of the local operator.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    operator_actions = operator.add_subparsers(dest="action", metavar="<action>")

    operator_set = operator_actions.add_parser(
        "set",
        help="store the operator name",
        description="Store the local operator name in ./litholog.json.",
    )
    operator_set.add_argument(
        "--name", metavar="<name>", help="operator name, required and non-empty"
    )
    operator_set.set_defaults(handler=command_operator_set)

    whoami = subparsers.add_parser(
        "whoami",
        help="print the stored operator name",
        description="Print the operator name stored in ./litholog.json.",
    )
    whoami.set_defaults(handler=command_whoami)

    for group in (layer, fossil, operator):
        group.set_defaults(group_parser=group)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        # `litholog` with no command, or `litholog layer` with no action: usage
        # summary and exit 2, never a traceback.
        target = getattr(args, "group_parser", None) or parser
        target.print_help(sys.stderr)
        return 2
    try:
        return handler(args, Printer(args.color == "always"))
    except UsageError as exc:
        _fail(str(exc))
        return 1
    except StoreError as exc:
        _fail(str(exc))
        return 1
    except BrokenPipeError:
        # `litholog column | head` is a normal thing to do with a column.
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0
    except Exception as exc:  # pragma: no cover - the no-traceback guarantee
        # The product contract is exactly one 'Error:' line, never a traceback.
        # Rerun with LITHOLOG_TRACEBACK=1 to see the full stack while developing.
        if os.environ.get("LITHOLOG_TRACEBACK"):
            raise
        _fail(f"unexpected failure ({exc.__class__.__name__})")
        return 1


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
