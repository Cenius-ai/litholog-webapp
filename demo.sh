#!/usr/bin/env bash
#
# LithoLog end-to-end demo - non-interactive, offline, no TTY required.
#
# It logs a small measured section from scratch in a throwaway directory,
# renders the stratigraphic column, registers fossil finds, labels the store
# with the local operator, and finally proves the no-traceback guarantee on a
# hand-corrupted store. Run it from anywhere:  bash demo.sh
#
set -euo pipefail
cd "$(dirname "$0")"

TOOL="$(pwd)/litholog.py"

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# Every command is shown exactly as the operator would type it.
show() { printf '$ %s\n' "$*"; }

litholog() { python3 "$TOOL" "$@"; }

# Run a command that must fail with exit status 1 and exactly one stderr line.
expect_error() {
  local expected="$1"
  shift
  local output status
  set +e
  output="$(python3 "$TOOL" "$@" 2>&1 >/dev/null)"
  status=$?
  set -e
  if [ "$status" -ne 1 ]; then
    printf 'demo FAILED: %s exited %s, expected 1\n' "$*" "$status" >&2
    exit 1
  fi
  if [ "$output" != "$expected" ]; then
    printf 'demo FAILED: %s printed "%s", expected "%s"\n' "$*" "$output" "$expected" >&2
    exit 1
  fi
  show "litholog $*"
  printf '%s\n' "$output"
}

printf 'LithoLog demo - measured section, stratigraphic column, fossil register\n'
printf 'working directory: %s (a scratch copy; the real store is ./litholog.json)\n' "$WORK"
printf '\n'
cd "$WORK"

printf '== 1. Log a measured section (top of section first) ==\n'
show 'litholog layer add --lithology mudstone --thickness 1.4 --description "grey-green blocky mudstone, root traces"'
litholog layer add --lithology mudstone --thickness 1.4 --description "grey-green blocky mudstone, root traces"
show 'litholog layer add --lithology sandstone --thickness 2.6 --description "cross-bedded, fine to medium grained"'
litholog layer add --lithology sandstone --thickness 2.6 --description "cross-bedded, fine to medium grained"
show 'litholog layer add --lithology siltstone --thickness 0.8 --description "bioturbated siltstone with plant debris"'
litholog layer add --lithology siltstone --thickness 0.8 --description "bioturbated siltstone with plant debris"
show 'litholog layer add --lithology coal --thickness 0.35 --description "bright banded coal seam"'
litholog layer add --lithology coal --thickness 0.35 --description "bright banded coal seam"
show 'litholog layer add --lithology limestone --thickness 0.9 --description "argillaceous limestone with shell hash"'
litholog layer add --lithology limestone --thickness 0.9 --description "argillaceous limestone with shell hash"
show 'litholog layer add --lithology shale --thickness 2.2 --description "fissile dark shale, ammonites in the upper 0.3 m"'
litholog layer add --lithology shale --thickness 2.2 --description "fissile dark shale, ammonites in the upper 0.3 m"
printf '\n'

printf '== 2. Read the register back ==\n'
show 'litholog layer list'
litholog layer list
printf '\n'

printf '== 3. Draw the stratigraphic column (one row per 0.5 m) ==\n'
show 'litholog column'
litholog column
printf '\n'

printf '== 4. Register fossil finds against measured depth ==\n'
show 'litholog fossil add --taxon Ammonite --depth 6.9'
litholog fossil add --taxon Ammonite --depth 6.9
show 'litholog fossil add --taxon Belemnite --depth 0.6'
litholog fossil add --taxon Belemnite --depth 0.6
show 'litholog fossil add --taxon Crinoid --depth 2.1'
litholog fossil add --taxon Crinoid --depth 2.1
show 'litholog fossil add --taxon "Plant fragment" --depth 3.5'
litholog fossil add --taxon "Plant fragment" --depth 3.5
show 'litholog fossil list'
litholog fossil list
printf '\n'

printf '== 5. Label the store with the local operator ==\n'
show 'litholog operator set --name "Jane Doe"'
litholog operator set --name "Jane Doe"
show 'litholog whoami'
litholog whoami
printf '\n'

printf '== 6. Bad input is one line, exit 1, and never writes ==\n'
expect_error 'Error: --lithology must be one of shale, sandstone, limestone, mudstone, siltstone, conglomerate, coal' \
  layer add --lithology granite --thickness 1.0
expect_error 'Error: --thickness must be a number' layer add --lithology shale --thickness abc
expect_error 'Error: --thickness must be greater than 0' layer add --lithology shale --thickness -2
expect_error 'Error: --taxon is required' fossil add --depth 4.5
expect_error 'Error: --depth must not be negative' fossil add --taxon Brachiopod --depth -1
expect_error 'Error: --name must not be empty' operator set --name ""
show 'litholog layer list | tail -1'
litholog layer list | tail -1
printf '\n'

printf '== 7. A hand-corrupted store is refused, never overwritten ==\n'
mkdir -p broken
printf '{\n  "version": 1,\n  "layers": [\n    { "id": "L1", "lithology": "shale", "thickness_m": 1.2\n' > broken/litholog.json
cp broken/litholog.json broken/litholog.json.expected
cd broken
expect_error 'Error: cannot read litholog.json' layer list
if cmp -s litholog.json litholog.json.expected; then
  printf '(the corrupted file is byte-identical to before the failed read)\n'
else
  printf 'demo FAILED: the corrupted store was modified\n' >&2
  exit 1
fi
cd "$WORK"
printf '\n'

printf '== 8. The store is one hand-editable JSON file ==\n'
show 'head -20 litholog.json'
head -20 litholog.json
printf '\n'
printf 'Demo complete\n'
litholog layer list | tail -1
litholog fossil list | tail -1
printf 'Store used for this run: %s/litholog.json (removed on exit)\n' "$WORK"
