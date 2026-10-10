#!/usr/bin/env bash
#
# LithoLog install: verify the interpreter, check the single source file, and
# seed a demo measured section into ./litholog.json if you do not have one yet.
#
# LithoLog itself has NO runtime dependencies - it is one standard-library
# Python file. This script never installs a system package, never needs sudo,
# never prompts, and never starts anything in the foreground. Run it with
# `bash install.sh` and it exits; the tool is then ready to use.
#
set -euo pipefail
cd "$(dirname "$0")"

printf 'LithoLog install\n'

# 1. Interpreter. Python 3.9 or newer; nothing else is required.
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Error: python3 was not found on PATH. Install Python 3.9+ (see INSTALL.md).\n' >&2
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
  printf 'Error: LithoLog needs Python 3.9 or newer; found %s\n' "$(python3 -V 2>&1)" >&2
  exit 1
fi
printf 'ok: %s\n' "$(python3 -V 2>&1)"

# 2. The whole tool is one file: compile it and import it so a broken checkout
#    fails loudly here instead of at the first command.
python3 -m py_compile litholog.py
python3 -c 'import litholog'
printf 'ok: litholog.py compiles and imports\n'

# 3. Project-level dependencies: none at runtime. The optional test runner from
#    requirements-dev.txt is installed only when it is missing, and a failed
#    optional install never breaks the tool - the suite also runs on the
#    standard-library unittest runner.
if python3 -c 'import pytest' >/dev/null 2>&1; then
  printf 'ok: pytest available for the test suite\n'
else
  printf 'note: pytest not found; installing the optional dev dependency\n'
  if python3 -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt; then
    printf 'ok: pytest installed\n'
  else
    printf 'note: could not install pytest (offline?); run the suite with:\n'
    printf '      python3 -m unittest discover -s tests -v\n'
  fi
fi

# 4. Seed a demo measured section, but only when there is no store yet, so
#    re-running this script never duplicates or overwrites your own section.
if [ -f litholog.json ]; then
  printf 'ok: litholog.json already present; leaving your section untouched\n'
else
  python3 litholog.py operator set --name "Jane Doe" >/dev/null
  python3 litholog.py layer add --lithology mudstone --thickness 1.4 \
    --description "grey-green blocky mudstone, root traces" >/dev/null
  python3 litholog.py layer add --lithology sandstone --thickness 2.6 \
    --description "cross-bedded, fine to medium grained, sharp top" >/dev/null
  python3 litholog.py layer add --lithology siltstone --thickness 0.8 \
    --description "bioturbated siltstone with plant debris" >/dev/null
  python3 litholog.py layer add --lithology coal --thickness 0.35 \
    --description "bright banded coal seam" >/dev/null
  python3 litholog.py layer add --lithology mudstone --thickness 1.1 \
    --description "carbonaceous mudstone, pyritic nodules" >/dev/null
  python3 litholog.py layer add --lithology limestone --thickness 0.9 \
    --description "argillaceous limestone with shell hash" >/dev/null
  python3 litholog.py layer add --lithology shale --thickness 2.2 \
    --description "fissile dark shale, ammonites in the upper 0.3 m" >/dev/null
  python3 litholog.py layer add --lithology sandstone --thickness 3.4 \
    --description "amalgamated sandstone, hummocky cross-stratification" >/dev/null
  python3 litholog.py fossil add --taxon Belemnite --depth 0.6 >/dev/null
  python3 litholog.py fossil add --taxon Crinoid --depth 2.1 >/dev/null
  python3 litholog.py fossil add --taxon "Plant fragment" --depth 3.5 >/dev/null
  python3 litholog.py fossil add --taxon Ammonite --depth 6.9 >/dev/null
  python3 litholog.py fossil add --taxon Brachiopod --depth 8.4 >/dev/null
  python3 litholog.py fossil add --taxon Bivalve --depth 11.9 >/dev/null
  printf 'ok: seeded a demo measured section into ./litholog.json\n'
fi

# 5. Prove the seeded store reads back.
python3 litholog.py whoami
python3 litholog.py layer list | tail -1
python3 litholog.py fossil list | tail -1

printf '\nInstall complete. Try:\n'
printf '  python3 litholog.py layer list\n'
printf '  python3 litholog.py column\n'
printf '  bash demo.sh          # full end-to-end run in a scratch directory\n'
printf '  python3 -m pytest     # tests (or: python3 -m unittest discover -s tests -v)\n'
