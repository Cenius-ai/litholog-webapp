# Installing LithoLog

LithoLog is one standard-library Python file plus a test suite. There is exactly
one sub-project (the repository root: `litholog.py`, `main.py`, `demo.sh`,
`install.sh`, `tests/`) and there is nothing to build, compile or bundle.

## Prerequisites (system level - install these yourself, the script will not)

| Requirement | Why | Check |
| --- | --- | --- |
| Python 3.9 or newer | runs `litholog.py` | `python3 -V` |
| A UTF-8 capable terminal | plain ASCII output | `locale` |
| pip (optional) | only to install the pytest test runner | `python3 -m pip --version` |

Nothing else is needed: no compiler, no `libsqlite3-dev`, no database engine, no
Node, no virtualenv, no system package. `install.sh` never calls `sudo`,
`apt-get`, `apk`, `yum` or `brew`, and never starts a service.

Package manager: **pip**, and only for the optional dev dependency in
`requirements-dev.txt`. There is no lockfile to install because the product has
no runtime dependencies at all.

## Step 1 - install and seed in one command

```bash
bash install.sh
```

It runs these steps, in order, and then **exits** (it never starts a long-running
process):

1. verifies `python3` is present and 3.9+;
2. compiles and imports `litholog.py`, so a broken checkout fails here instead of
   at your first command;
3. installs the optional test runner from `requirements-dev.txt` with
   `python3 -m pip install -r requirements-dev.txt` **only if `pytest` is missing**
   (if that optional install cannot reach a registry, the script says so and
   continues - the suite also runs on the standard-library `unittest` runner);
4. seeds a demo measured section (see step 2);
5. prints the seeded store back (`whoami`, `Layers: N`, `Fossils: N`).

It is idempotent: run it as often as you like.

## Step 2 - the seed (its own step, and it is not required)

The seed writes a realistic demo section - eight described layers from 1.4 m
mudstone to 3.4 m sandstone, six fossil finds from a belemnite at 0.6 m to a
bivalve at 11.9 m, and the operator label `Jane Doe` - into `./litholog.json` in
this directory, using LithoLog's own `layer add` / `fossil add` / `operator set`
commands.

- It only runs when `./litholog.json` does **not** exist, so it can never
  duplicate or overwrite a section you have recorded.
- To get the demo section back: `rm litholog.json && bash install.sh`.
- To skip the seed entirely: just delete `litholog.json` and start recording -
  every command works on an empty directory and creates the store on first write.

The store is a plain file you can copy, diff or hand-edit; there is no migration
step, because `version` is the only schema marker and it is currently `1`.

## Step 3 - run it

```bash
python3 litholog.py layer list
python3 litholog.py column
python3 litholog.py layer add --lithology shale --thickness 1.2 --description "fissile dark shale"
python3 litholog.py fossil add --taxon Ammonite --depth 4.5
python3 litholog.py fossil list
python3 litholog.py operator set --name "Jane Doe"
python3 litholog.py whoami
```

The store is always `./litholog.json` in the directory you run the command from.
There is no config file, no environment variable and no `--file` flag. It is a
short-lived command, not a server: every invocation reads, writes and exits.

`python3 litholog.py --help` lists the commands; `python3 main.py <command>` is an
equivalent entry point. `bash demo.sh` runs the whole product end to end in a
throwaway directory.

## Step 4 - test

```bash
python3 -m pytest                        # pip install -r requirements-dev.txt first
python3 -m unittest discover -s tests -v # the same suite, no dependency at all
```

Both runners are expected to end green: the suite drives the real CLI as a
subprocess in a temporary working directory.

## What gets created, and how to remove it

| Path | Created by | Safe to delete? |
| --- | --- | --- |
| `./litholog.json` (in the directory you work in) | first `add`/`set` command | yes - it is your data, back it up first |
| `__pycache__/` | Python imports | yes |
| `.pytest_cache/` | pytest | yes |

Final clean-up: `rm -rf __pycache__ .pytest_cache litholog.json`.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Error: cannot read litholog.json` | the file is truncated, hand-edited into invalid JSON, or unreadable | fix the JSON by hand (it is `indent=2`) or restore your backup; LithoLog never overwrites an unreadable store |
| `Error: --lithology must be one of ...` | a lithology outside the seven keywords | use `shale`, `sandstone`, `limestone`, `mudstone`, `siltstone`, `conglomerate` or `coal` |
| `Error: --thickness must be a number` | a non-numeric `--thickness` | pass metres, e.g. `--thickness 1.2` |
| exit status `2` | usage error: unknown command, missing action, unknown flag | run `python3 litholog.py --help` |
| the demo script prints `demo FAILED` | the CLI no longer matches the documented contract | report the failing step; `python3 -m pytest` reproduces it |
