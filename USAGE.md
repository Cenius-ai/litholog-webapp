# Using LithoLog

Everything is invoked as `litholog <group> <action> [flags]`; run
`python3 litholog.py <group> <action> --help` for the flags of any action. Every
transcript below is real output: the two-bed examples use a scratch store, and the
column walkthrough uses the eight-layer demo section `install.sh` seeds
(12.75 m total).

- [Layer register](#layer-register) - `layer add`, `layer list`
- [Stratigraphic column](#stratigraphic-column) - `column`
- [Fossil find register](#fossil-find-register) - `fossil add`, `fossil list`
- [Operator profile](#operator-profile) - `operator set`, `whoami`
- [Errors, exit codes and scripting](#errors-exit-codes-and-scripting)

## Layer register

Log a bed by describing it. The lithology must be one of the seven known
keywords, because the column needs exactly one glyph per lithology, and the
thickness must be a number of metres greater than zero.

```console
$ python3 litholog.py layer add --lithology shale --thickness 1.2 --description "fissile dark shale"
Added layer L1 (shale, 1.2 m)
$ python3 litholog.py layer add --lithology sandstone --thickness 3.8
Added layer L2 (sandstone, 3.8 m)
```

Ids are assigned for you (`L1`, `L2`, ...) and never reused - the register is
append-only. Read it back in insertion order, top of section first:

```console
$ python3 litholog.py layer list
ID  LITHOLOGY  THICKNESS  DESCRIPTION
--  ---------  ---------  ------------------
L1  shale      1.2 m      fissile dark shale
L2  sandstone  3.8 m      -
Layers: 2
```

The demo section seeded by `install.sh` reads like this - take it as the shape of a
real measured section, then delete `litholog.json` and record your own:

```console
$ python3 litholog.py layer list
ID  LITHOLOGY  THICKNESS  DESCRIPTION
--  ---------  ---------  ----------------------------------------------------
L1  mudstone   1.4 m      grey-green blocky mudstone, root traces
L2  sandstone  2.6 m      cross-bedded, fine to medium grained, sharp top
L3  siltstone  0.8 m      bioturbated siltstone with plant debris
L4  coal       0.35 m     bright banded coal seam
L5  mudstone   1.1 m      carbonaceous mudstone, pyritic nodules
L6  limestone  0.9 m      argillaceous limestone with shell hash
L7  shale      2.2 m      fissile dark shale, ammonites in the upper 0.3 m
L8  sandstone  3.4 m      amalgamated sandstone, hummocky cross-stratification
Layers: 8
```

A layer recorded without `--description` shows `-`. With no layers recorded at
all, the register invites the first one instead of printing an empty table:

```console
$ python3 litholog.py layer list
No layers recorded yet. Add one with: litholog layer add --lithology shale --thickness 1.0
```

## Stratigraphic column

`column` draws the whole section top-down under a cumulative depth ruler starting
at 0.0 m: one row per 0.5 m of bed, rounded up, so a 0.2 m bed is still visible as
a single row. Each row carries its depth span, the bar of that lithology's
pattern character, the keyword and the bed's own thickness.

```console
$ python3 litholog.py column
Stratigraphic column - 8 layers, total 12.75 m
0.0-0.5 m      ---      mudstone   1.4 m
0.5-1.0 m      ---      mudstone   1.4 m
1.0-1.4 m      ---      mudstone   1.4 m
1.4-1.9 m      ......   sandstone  2.6 m
1.9-2.4 m      ......   sandstone  2.6 m
2.4-2.9 m      ......   sandstone  2.6 m
2.9-3.4 m      ......   sandstone  2.6 m
3.4-3.9 m      ......   sandstone  2.6 m
3.9-4.0 m      ......   sandstone  2.6 m
4.0-4.5 m      ::       siltstone  0.8 m
4.5-4.8 m      ::       siltstone  0.8 m
4.8-5.15 m     @        coal       0.35 m
5.15-5.65 m    ---      mudstone   1.1 m
5.65-6.15 m    ---      mudstone   1.1 m
6.15-6.25 m    ---      mudstone   1.1 m
6.25-6.75 m    ##       limestone  0.9 m
6.75-7.15 m    ##       limestone  0.9 m
7.15-7.65 m    =====    shale      2.2 m
7.65-8.15 m    =====    shale      2.2 m
8.15-8.65 m    =====    shale      2.2 m
8.65-9.15 m    =====    shale      2.2 m
9.15-9.35 m    =====    shale      2.2 m
9.35-9.85 m    .......  sandstone  3.4 m
9.85-10.35 m   .......  sandstone  3.4 m
10.35-10.85 m  .......  sandstone  3.4 m
10.85-11.35 m  .......  sandstone  3.4 m
11.35-11.85 m  .......  sandstone  3.4 m
11.85-12.35 m  .......  sandstone  3.4 m
12.35-12.75 m  .......  sandstone  3.4 m
```

| lithology | shale | sandstone | limestone | mudstone | siltstone | conglomerate | coal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pattern | `=` | `.` | `#` | `-` | `:` | `o` | `@` |

With no layers recorded, `column` prints the same hint as `layer list` and exits
0. The terminal is the only output surface - there is no image, SVG or PDF
export, and fossils are deliberately not drawn inside the column (they are a
separate register).

## Fossil find register

Register a find against its measured depth. The taxon is required and may not be
blank; the depth is metres and may be zero, but never negative.

```console
$ python3 litholog.py fossil add --taxon Ammonite --depth 6.9
Added fossil F1 (Ammonite at 6.9 m)
$ python3 litholog.py fossil add --taxon Belemnite --depth 0.6
Added fossil F2 (Belemnite at 0.6 m)
```

Finds are stored in the order you add them and listed shallowest first, so the
register reads down the section:

```console
$ python3 litholog.py fossil list
ID  TAXON       DEPTH
--  ----------  -----
F2  Belemnite   0.6 m
F1  Ammonite   6.9 m
Fossils: 2
```

The seeded demo register holds six finds the same way (belemnite 0.6 m, crinoid
2.1 m, plant fragment 3.5 m, ammonite 6.9 m, brachiopod 8.4 m, bivalve 11.9 m,
`Fossils: 6`).

Empty register:

```console
$ python3 litholog.py fossil list
No fossils recorded yet. Add one with: litholog fossil add --taxon Ammonite --depth 1.2
```

## Operator profile

The offline stand-in for sign-in: label this store with your name. Nothing is
gated, there is no password, no session and no token - the tool stays usable with
zero setup.

```console
$ python3 litholog.py operator set --name "Jane Doe"
Operator set to Jane Doe
$ python3 litholog.py whoami
Operator: Jane Doe
```

No operator yet:

```console
$ python3 litholog.py whoami
No operator set. Set one with: litholog operator set --name "Jane Doe"
```

## Errors, exit codes and scripting

Every rejected input is exactly one `Error: ...` line on **stderr**, exit status
`1`, and no write at all - your section is untouched:

```console
$ python3 litholog.py layer add --lithology granite --thickness 1.0
Error: --lithology must be one of shale, sandstone, limestone, mudstone, siltstone, conglomerate, coal
$ python3 litholog.py layer add --lithology shale --thickness abc
Error: --thickness must be a number
$ python3 litholog.py layer add --lithology shale --thickness -2
Error: --thickness must be greater than 0
$ python3 litholog.py fossil add --taxon Brachiopod --depth -1
Error: --depth must not be negative
$ python3 litholog.py operator set --name ""
Error: --name must not be empty
```

A store that cannot be read, parsed or validated is refused with the same
one-line shape, and never overwritten - not even by `operator set`, so a
hand-editing typo cannot cost you the rest of the section:

```console
$ python3 litholog.py layer list
Error: cannot read litholog.json
```

| exit status | meaning |
| --- | --- |
| `0` | success, including the empty-state hints |
| `1` | a rejected flag, or an unreadable/unwritable `litholog.json` |
| `2` | usage error: unknown command, missing action, unknown flag |

Results go to stdout, errors to stderr, and output is deterministic plain ASCII,
so the tool composes with ordinary shell tools:

```bash
python3 litholog.py column | head -5          # the top of the section
python3 litholog.py column | less             # page through a long section
python3 litholog.py layer list | tail -1      # just the bed count
python3 litholog.py fossil add --taxon Belemnite --depth 3.2 && python3 litholog.py fossil list
```

`--color=always` paints the primary status lines (add confirmations, the count
lines, the column header) with the product's accent; it is off by default so
transcripts stay byte-for-byte diffable, and no status is ever signalled by
colour alone.

## The store

`./litholog.json` is pretty-printed `indent=2` JSON, written atomically through a
temporary file and `os.replace`, so an interrupted write leaves the previous valid
store in place. Extra keys you add by hand are preserved across writes.

```json
{
  "version": 1,
  "operator": "Jane Doe",
  "layers": [
    {
      "id": "L1",
      "lithology": "shale",
      "thickness_m": 1.2,
      "description": "fissile dark shale"
    }
  ],
  "fossils": [
    { "id": "F1", "taxon": "Ammonite", "depth_m": 4.5 }
  ]
}
```

The `version` field is the schema marker (currently `1`); `layers` are in
stratigraphic order, top of section first; `fossils` are stored in insertion
order and sorted by depth only for display.
