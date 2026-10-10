"""LithoLog acceptance tests.

The suite drives the real CLI as a subprocess inside a throwaway working
directory, because the store path (./litholog.json in the current directory) and
the process contract (stdout vs stderr, exit status 0/1/2) are the product.

Runs green with either runner:

    python3 -m pytest
    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "litholog.py"
sys.path.insert(0, str(REPO_ROOT))

import litholog  # the tool under test, imported from the repo root

ROW_RE = re.compile(
    r"^(?P<span>\S+-\S+ m)\s+(?P<pattern>\S+)\s+(?P<lithology>\S+)\s+(?P<thickness>\S+ m)$"
)
STORE = "litholog.json"
LAYER_EMPTY_HINT = (
    "No layers recorded yet. Add one with: litholog layer add --lithology shale --thickness 1.0"
)
FOSSIL_EMPTY_HINT = (
    "No fossils recorded yet. Add one with: litholog fossil add --taxon Ammonite --depth 1.2"
)
OPERATOR_EMPTY_HINT = 'No operator set. Set one with: litholog operator set --name "Jane Doe"'


def run(workdir: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    """Run the CLI in `workdir` and capture both streams as text."""
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        check=False,
    )


def read_store(workdir: pathlib.Path) -> dict:
    return json.loads((workdir / STORE).read_text(encoding="utf-8"))


def write_store(workdir: pathlib.Path, data: dict) -> None:
    (workdir / STORE).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def layers_store(count: int, thickness: float = 0.7) -> dict:
    return {
        "version": 1,
        "operator": None,
        "layers": [
            {
                "id": f"L{index}",
                "lithology": "shale",
                "thickness_m": thickness,
                "description": "",
            }
            for index in range(1, count + 1)
        ],
        "fossils": [],
    }


class TempDirCase(unittest.TestCase):
    """Base case that gives every test its own empty working directory."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.workdir = pathlib.Path(self._temp.name)
        self.addCleanup(self._temp.cleanup)


# --------------------------------------------------------------------------- #
# T1 - store handling
# --------------------------------------------------------------------------- #


class StoreHandlingTests(TempDirCase):
    def test_empty_list_prints_hint_and_creates_nothing(self) -> None:
        result = run(self.workdir, "layer", "list")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), LAYER_EMPTY_HINT)
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.workdir / STORE).exists())

    def test_missing_store_reads_as_empty_for_every_reader(self) -> None:
        for args, expected in (
            (("column",), LAYER_EMPTY_HINT),
            (("fossil", "list"), FOSSIL_EMPTY_HINT),
            (("whoami",), OPERATOR_EMPTY_HINT),
        ):
            with self.subTest(args=args):
                result = run(self.workdir, *args)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), expected)

    def test_malformed_store_is_one_error_line_and_leaves_bytes_alone(self) -> None:
        target = self.workdir / STORE
        target.write_text('{"version": 1, "layers": [{"id": "L1", ', encoding="utf-8")
        before = target.read_bytes()
        for args in (
            ("layer", "list"),
            ("column",),
            ("fossil", "list"),
            ("whoami",),
            ("layer", "add", "--lithology", "coal", "--thickness", "0.4"),
            ("operator", "set", "--name", "Jane Doe"),
        ):
            with self.subTest(args=args):
                result = run(self.workdir, *args)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, f"Error: cannot read {STORE}\n")
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(target.read_bytes(), before)

    def test_unreadable_store_is_refused(self) -> None:
        # A directory in the store's place is unreadable for root and non-root alike.
        (self.workdir / STORE).mkdir()
        result = run(self.workdir, "layer", "list")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, f"Error: cannot read {STORE}\n")
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue((self.workdir / STORE).is_dir())

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_store_without_read_permission_is_refused(self) -> None:
        target = self.workdir / STORE
        target.write_text('{"version": 1, "operator": null, "layers": [], "fossils": []}\n')
        target.chmod(0o000)
        self.addCleanup(target.chmod, 0o644)
        result = run(self.workdir, "layer", "list")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, f"Error: cannot read {STORE}\n")

    def test_store_is_parsed_as_strict_json_only(self) -> None:
        # The store is read by a strict JSON text parser: anything that is not
        # real JSON is refused, and a payload that names a Python call is just
        # unreadable text that changes nothing on disk.
        payloads = (
            "{'version': 1, 'operator': None, 'layers': [], 'fossils': []}",
            '{"version": 1, "operator": null, "layers": [], "fossils": []} trailing',
            '{"version": 1, "operator": null, "layers": [], "fossils": [], "x": __import__("os")}',
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                (self.workdir / STORE).write_text(payload, encoding="utf-8")
                result = run(self.workdir, "layer", "list")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, f"Error: cannot read {STORE}\n")
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual((self.workdir / STORE).read_text(encoding="utf-8"), payload)

    def test_hand_edited_store_is_preserved_and_extended(self) -> None:
        write_store(
            self.workdir,
            {
                "version": 1,
                "operator": "Jane Doe",
                "custom_note": "rounded up by hand",
                "layers": [
                    {"id": "L1", "lithology": "shale", "thickness_m": 1.5, "description": "blocky"},
                    {"id": "L2", "lithology": "limestone", "thickness_m": 0.8, "description": ""},
                ],
                "fossils": [],
            },
        )
        result = run(self.workdir, "layer", "add", "--lithology", "coal", "--thickness", "0.4")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = read_store(self.workdir)
        self.assertEqual([layer["id"] for layer in data["layers"]], ["L1", "L2", "L3"])
        self.assertEqual(data["layers"][2]["lithology"], "coal")
        self.assertEqual(data["operator"], "Jane Doe")
        self.assertEqual(data["custom_note"], "rounded up by hand")
        self.assertEqual(sorted(os.listdir(self.workdir)), [STORE])

    def test_store_is_a_normal_hand_editable_file(self) -> None:
        import stat

        run(self.workdir, "layer", "add", "--lithology", "shale", "--thickness", "1.2")
        mode = stat.S_IMODE((self.workdir / STORE).stat().st_mode)
        self.assertEqual(mode & 0o600, 0o600, "owner read and write")

    def test_store_is_written_as_readable_indent_two_json(self) -> None:
        run(self.workdir, "layer", "add", "--lithology", "shale", "--thickness", "1.2")
        text = (self.workdir / STORE).read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertIn('\n  "version": 1,\n', text)
        self.assertIn('"operator": null', text)


# --------------------------------------------------------------------------- #
# T2 - layer add
# --------------------------------------------------------------------------- #


class LayerAddTests(TempDirCase):
    def test_add_stores_every_field(self) -> None:
        result = run(
            self.workdir,
            "layer",
            "add",
            "--lithology",
            "shale",
            "--thickness",
            "1.2",
            "--description",
            "fissile dark shale",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Added layer L1 (shale, 1.2 m)\n")
        data = read_store(self.workdir)
        self.assertEqual(
            data["layers"][0],
            {
                "id": "L1",
                "lithology": "shale",
                "thickness_m": 1.2,
                "description": "fissile dark shale",
            },
        )

    def test_ids_increment_from_existing_layers(self) -> None:
        run(self.workdir, "layer", "add", "--lithology", "shale", "--thickness", "1.0")
        run(self.workdir, "layer", "add", "--lithology", "mudstone", "--thickness", "2.0")
        result = run(self.workdir, "layer", "add", "--lithology", "sandstone", "--thickness", "3.0")
        self.assertEqual(result.stdout, "Added layer L3 (sandstone, 3.0 m)\n")
        listed = run(self.workdir, "layer", "list")
        self.assertEqual(listed.stdout.splitlines()[-1], "Layers: 3")
        self.assertEqual(read_store(self.workdir)["layers"][2]["id"], "L3")

    def test_every_documented_bad_flag_is_one_error_line_and_no_write(self) -> None:
        target = self.workdir / STORE
        cases = (
            (
                ("--lithology", "granite", "--thickness", "1.0"),
                (
                    "Error: --lithology must be one of shale, sandstone, limestone, "
                    "mudstone, siltstone, conglomerate, coal"
                ),
            ),
            (("--lithology", "shale", "--thickness", "abc"), "Error: --thickness must be a number"),
            (
                ("--lithology", "shale", "--thickness", "0"),
                "Error: --thickness must be greater than 0",
            ),
            (
                ("--lithology", "shale", "--thickness", "-2"),
                "Error: --thickness must be greater than 0",
            ),
            (("--thickness", "1.0"), "Error: --lithology is required"),
        )
        for flags, expected in cases:
            with self.subTest(flags=flags):
                result = run(self.workdir, "layer", "add", *flags)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, expected + "\n")
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(target.exists())

    def test_thickness_is_validated_before_the_store_is_read(self) -> None:
        (self.workdir / STORE).write_text("{ not json", encoding="utf-8")
        result = run(self.workdir, "layer", "add", "--lithology", "granite", "--thickness", "1.0")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "Error: --lithology must be one of shale, sandstone, limestone, "
            "mudstone, siltstone, conglomerate, coal\n",
        )


# --------------------------------------------------------------------------- #
# T3 - layer list
# --------------------------------------------------------------------------- #


class LayerListTests(TempDirCase):
    def test_rows_show_id_lithology_thickness_and_description(self) -> None:
        run(
            self.workdir,
            "layer",
            "add",
            "--lithology",
            "shale",
            "--thickness",
            "1.2",
            "--description",
            "fissile dark shale",
        )
        run(self.workdir, "layer", "add", "--lithology", "sandstone", "--thickness", "3.8")
        result = run(self.workdir, "layer", "list")
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], "Layers: 2")
        # header, rule, one row per layer, count line
        self.assertEqual(len(lines), 5)
        self.assertIn("L1", lines[2])
        self.assertIn("shale", lines[2])
        self.assertIn("1.2 m", lines[2])
        self.assertIn("fissile dark shale", lines[2])
        self.assertIn("L2", lines[3])
        self.assertIn("sandstone", lines[3])
        self.assertIn("3.8 m", lines[3])

    def test_empty_state_asks_for_the_first_layer(self) -> None:
        result = run(self.workdir, "layer", "list")
        self.assertEqual(result.stdout.strip(), LAYER_EMPTY_HINT)
        self.assertEqual(result.returncode, 0)

    def test_three_hundred_layers_list_in_order_under_a_second(self) -> None:
        write_store(self.workdir, layers_store(300))
        started = time.monotonic()
        result = run(self.workdir, "layer", "list")
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0)
        self.assertLess(elapsed, 1.0, f"layer list took {elapsed:.3f}s")
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], "Layers: 300")
        self.assertIn("L1", lines[2])
        self.assertIn("L300", lines[-2])


# --------------------------------------------------------------------------- #
# T4 - column
# --------------------------------------------------------------------------- #


class ColumnTests(TempDirCase):
    def record(self, lithology: str, thickness: str) -> None:
        result = run(
            self.workdir, "layer", "add", "--lithology", lithology, "--thickness", thickness
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_header_counts_layers_and_totals_thickness(self) -> None:
        self.record("shale", "2.0")
        self.record("sandstone", "3.0")
        result = run(self.workdir, "column")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout.splitlines()[0], "Stratigraphic column - 2 layers, total 5.0 m"
        )

    def test_each_lithology_uses_its_own_pattern_character(self) -> None:
        for lithology in litholog.LITHOLOGY_KEYWORDS:
            self.record(lithology, "0.6")
        output = run(self.workdir, "column").stdout
        seen: dict[str, set[str]] = {}
        for line in output.splitlines()[1:]:
            match = ROW_RE.match(line)
            self.assertIsNotNone(match, line)
            seen.setdefault(match.group("lithology"), set()).add(match.group("pattern"))
        self.assertEqual(sorted(seen), sorted(litholog.LITHOLOGY_KEYWORDS))
        for lithology, patterns in seen.items():
            self.assertEqual(len(patterns), 1, patterns)
            bar = patterns.pop()
            # a row's bar is that lithology's glyph repeated, never a mix
            self.assertEqual(set(bar), {litholog.LITHOLOGY_PATTERNS[lithology]})

    def test_patterns_are_one_to_one_with_the_keyword_list(self) -> None:
        patterns = list(litholog.LITHOLOGY_PATTERNS.values())
        self.assertEqual(sorted(litholog.LITHOLOGY_PATTERNS), sorted(litholog.LITHOLOGY_KEYWORDS))
        self.assertEqual(len(set(patterns)), len(patterns))
        self.assertTrue(all(len(pattern) == 1 for pattern in patterns))

    def test_depth_ruler_accumulates_in_insertion_order(self) -> None:
        self.record("shale", "2.0")
        self.record("sandstone", "3.0")
        rows = run(self.workdir, "column").stdout.splitlines()[1:]
        shale_rows = [row for row in rows if "shale" in row]
        sandstone_rows = [row for row in rows if "sandstone" in row]
        self.assertEqual(len(shale_rows), 4)
        self.assertEqual(len(sandstone_rows), 6)
        self.assertTrue(shale_rows[0].startswith("0.0-0.5 m"))
        self.assertTrue(sandstone_rows[0].startswith("2.0-2.5 m"))
        self.assertTrue(shale_rows[-1].startswith("1.5-2.0 m"))
        self.assertTrue(sandstone_rows[-1].startswith("4.5-5.0 m"))
        self.assertTrue(all("2.0 m" in row for row in shale_rows))
        self.assertTrue(all("3.0 m" in row for row in sandstone_rows))

    def test_thin_bed_still_gets_one_visible_row(self) -> None:
        self.record("siltstone", "0.2")
        lines = run(self.workdir, "column").stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("0.0-0.2 m", lines[1])
        self.assertIn(":", lines[1].split("  ")[1])
        self.assertIn("siltstone", lines[1])

    def test_empty_state_points_back_at_layer_add(self) -> None:
        result = run(self.workdir, "column")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), LAYER_EMPTY_HINT)

    def test_five_hundred_layers_render_within_two_seconds(self) -> None:
        write_store(self.workdir, layers_store(500))
        started = time.monotonic()
        result = run(self.workdir, "column")
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0)
        self.assertLess(elapsed, 2.0, f"column took {elapsed:.3f}s")
        self.assertEqual(
            result.stdout.splitlines()[0], "Stratigraphic column - 500 layers, total 350.0 m"
        )


# --------------------------------------------------------------------------- #
# T5 - fossil register
# --------------------------------------------------------------------------- #


class FossilTests(TempDirCase):
    def test_add_stores_taxon_and_depth(self) -> None:
        result = run(self.workdir, "fossil", "add", "--taxon", "Ammonite", "--depth", "4.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Added fossil F1 (Ammonite at 4.5 m)\n")
        self.assertEqual(
            read_store(self.workdir)["fossils"][0],
            {"id": "F1", "taxon": "Ammonite", "depth_m": 4.5},
        )

    def test_rejected_depth_leaves_the_register_byte_identical(self) -> None:
        run(self.workdir, "fossil", "add", "--taxon", "Ammonite", "--depth", "4.5")
        before = run(self.workdir, "fossil", "list").stdout
        stored_before = (self.workdir / STORE).read_bytes()
        result = run(self.workdir, "fossil", "add", "--taxon", "Ammonite", "--depth", "abc")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "Error: --depth must be a number\n")
        self.assertEqual((self.workdir / STORE).read_bytes(), stored_before)
        self.assertEqual(run(self.workdir, "fossil", "list").stdout, before)

    def test_bad_taxon_and_negative_depth_are_refused(self) -> None:
        for flags, expected in (
            (("--depth", "4.5"), "Error: --taxon is required"),
            (("--taxon", "  ", "--depth", "4.5"), "Error: --taxon is required"),
            (("--taxon", "Brachiopod", "--depth", "-1"), "Error: --depth must not be negative"),
            (("--taxon", "Brachiopod", "--depth", "shallow"), "Error: --depth must be a number"),
        ):
            with self.subTest(flags=flags):
                result = run(self.workdir, "fossil", "add", *flags)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, expected + "\n")
                self.assertFalse((self.workdir / STORE).exists())

    def test_zero_depth_is_a_valid_find(self) -> None:
        result = run(self.workdir, "fossil", "add", "--taxon", "Crinoid", "--depth", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Added fossil F1 (Crinoid at 0.0 m)\n")

    def test_list_sorts_by_depth_and_counts(self) -> None:
        run(self.workdir, "fossil", "add", "--taxon", "Ammonite", "--depth", "4.5")
        run(self.workdir, "fossil", "add", "--taxon", "Brachiopod", "--depth", "1.2")
        result = run(self.workdir, "fossil", "list")
        self.assertEqual(result.returncode, 0)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], "Fossils: 2")
        self.assertIn("Brachiopod", lines[2])
        self.assertIn("1.2 m", lines[2])
        self.assertIn("Ammonite", lines[3])
        self.assertIn("4.5 m", lines[3])

    def test_empty_state_asks_for_the_first_find(self) -> None:
        result = run(self.workdir, "fossil", "list")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), FOSSIL_EMPTY_HINT)


# --------------------------------------------------------------------------- #
# T6 - operator identity
# --------------------------------------------------------------------------- #


class OperatorTests(TempDirCase):
    def test_empty_state_hint(self) -> None:
        result = run(self.workdir, "whoami")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), OPERATOR_EMPTY_HINT)

    def test_set_then_whoami(self) -> None:
        result = run(self.workdir, "operator", "set", "--name", "Jane Doe")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "Operator set to Jane Doe\n")
        self.assertIn('"operator": "Jane Doe"', (self.workdir / STORE).read_text(encoding="utf-8"))
        self.assertEqual(read_store(self.workdir)["operator"], "Jane Doe")
        self.assertEqual(run(self.workdir, "whoami").stdout, "Operator: Jane Doe\n")

    def test_empty_name_is_refused_without_changing_the_operator(self) -> None:
        run(self.workdir, "operator", "set", "--name", "Jane Doe")
        stored_before = (self.workdir / STORE).read_bytes()
        cases = (
            (("--name", ""), "Error: --name must not be empty\n"),
            (("--name", "   "), "Error: --name must not be empty\n"),
            ((), "Error: --name is required\n"),
        )
        for flags, expected in cases:
            with self.subTest(flags=flags):
                result = run(self.workdir, "operator", "set", *flags)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, expected)
                self.assertEqual((self.workdir / STORE).read_bytes(), stored_before)

    def test_operator_is_kept_when_layers_change(self) -> None:
        run(self.workdir, "operator", "set", "--name", "Jane Doe")
        run(self.workdir, "layer", "add", "--lithology", "coal", "--thickness", "0.4")
        self.assertEqual(read_store(self.workdir)["operator"], "Jane Doe")
        self.assertEqual(run(self.workdir, "whoami").stdout, "Operator: Jane Doe\n")


# --------------------------------------------------------------------------- #
# T7 - help and the no-traceback guarantee
# --------------------------------------------------------------------------- #


class HelpAndHardeningTests(TempDirCase):
    def test_no_arguments_prints_usage_listing_every_command(self) -> None:
        result = run(self.workdir)
        self.assertEqual(result.returncode, 2)
        for name in ("layer", "fossil", "column", "operator", "whoami"):
            self.assertIn(name, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_command_prints_usage(self) -> None:
        result = run(self.workdir, "bogus")
        self.assertEqual(result.returncode, 2)
        for name in ("layer", "fossil", "column", "operator"):
            self.assertIn(name, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_group_without_action_prints_its_own_usage(self) -> None:
        result = run(self.workdir, "layer")
        self.assertEqual(result.returncode, 2)
        self.assertIn("add", result.stderr)
        self.assertIn("list", result.stderr)

    def test_layer_add_help_documents_every_flag(self) -> None:
        result = run(self.workdir, "layer", "add", "--help")
        self.assertEqual(result.returncode, 0)
        for flag in ("--lithology", "--thickness", "--description"):
            self.assertIn(flag, result.stdout)

    def test_version_flag(self) -> None:
        result = run(self.workdir, "--version")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("litholog "))

    def test_every_documented_bad_input_is_one_error_line_without_traceback(self) -> None:
        (self.workdir / STORE).write_text("{ broken", encoding="utf-8")
        cases = (
            (
                ("layer", "add", "--lithology", "granite", "--thickness", "1"),
                "--lithology must be one of",
            ),
            (
                ("layer", "add", "--lithology", "shale", "--thickness", "abc"),
                "--thickness must be a number",
            ),
            (
                ("fossil", "add", "--taxon", "Ammonite", "--depth", "abc"),
                "--depth must be a number",
            ),
            (
                ("fossil", "add", "--taxon", "Ammonite", "--depth", "-1"),
                "--depth must not be negative",
            ),
            (("layer", "add", "--thickness", "1"), "--lithology is required"),
            (("fossil", "add", "--depth", "1"), "--taxon is required"),
            (("operator", "set", "--name", ""), "--name must not be empty"),
            (
                (
                    "layer",
                    "list",
                ),
                f"cannot read {STORE}",
            ),
        )
        for args, fragment in cases:
            with self.subTest(args=args):
                result = run(self.workdir, *args)
                self.assertEqual(result.returncode, 1)
                stderr_lines = [line for line in result.stderr.splitlines() if line]
                self.assertEqual(len(stderr_lines), 1)
                self.assertTrue(stderr_lines[0].startswith("Error: "), stderr_lines)
                self.assertIn(fragment, stderr_lines[0])
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_default_output_carries_no_ansi_escape(self) -> None:
        run(self.workdir, "layer", "add", "--lithology", "shale", "--thickness", "1.2")
        for args in (("layer", "list"), ("column",), ("whoami",)):
            with self.subTest(args=args):
                result = run(self.workdir, *args)
                self.assertNotIn("\x1b", result.stdout)

    def test_color_is_opt_in_and_only_paints_status_lines(self) -> None:
        run(self.workdir, "layer", "add", "--lithology", "shale", "--thickness", "1.2")
        result = run(self.workdir, "--color=always", "layer", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], "\x1b[38;5;131mLayers: 1\x1b[0m")
        self.assertNotIn("\x1b", "\n".join(lines[:-1]))

    def test_main_py_is_an_equivalent_entry_point(self) -> None:
        shim = REPO_ROOT / "main.py"
        self.assertTrue(shim.exists())
        result = subprocess.run(
            [sys.executable, str(shim), "column"],
            cwd=str(self.workdir),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), LAYER_EMPTY_HINT)

    def test_every_shipped_python_file_compiles(self) -> None:
        for path in sorted(REPO_ROOT.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            with self.subTest(path=str(path)):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")


# --------------------------------------------------------------------------- #
# demonstrable form
# --------------------------------------------------------------------------- #


class DemoScriptTests(unittest.TestCase):
    def test_demo_runs_end_to_end_and_exits_zero(self) -> None:
        demo = REPO_ROOT / "demo.sh"
        self.assertTrue(demo.exists(), "demo.sh must ship at the project root")
        result = subprocess.run(
            ["bash", str(demo)], cwd=str(REPO_ROOT), capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Stratigraphic column -", result.stdout)
        self.assertIn("Layers:", result.stdout)
        self.assertIn("Fossils:", result.stdout)
        self.assertIn("Operator: Jane Doe", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)
        # the demo must never touch the project's own working directory
        self.assertFalse((REPO_ROOT / "__demo_store__").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
