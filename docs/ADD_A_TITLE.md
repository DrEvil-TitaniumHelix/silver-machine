# Add a title

> The worked example below is the Champions profile under `sm/titles/cok/`. It ships in the public source when that title ships; a source cut that does not include it yet still has the same contract in `sm/titles/ssb/` (older shape) and the files named here.


A title is a Python package under `sm/titles/`, called a **profile**. It reads the player's own game files, and the shared engine runs them. This page follows the most complete worked example, `sm/titles/cok/`. Read [DECISIONS.md](DECISIONS.md) first.

Throughout, `xyz` stands for your new title's id. It must be a lower-case Python identifier; `sm/titles/__init__.py` finds the package by that name, and there is no other registration.

## The two rules that are not negotiable

1. **No original bytes in the repository.** Game files, decompressed data, pictures and saves stay in the player's folder or in memory. The repository holds only sizes, offsets and SHA-256 hashes.
2. **No copied lines.** Decompiled or reconstructed source may be read as a reference to learn what the game does. Never copy or translate it line by line. `herdr/tools/source_guard.py` fails if any line of 6 or more tokens under `sm/` matches a reference clone.

Never guess a game fact. Take it from a reference or the game's own bytes, or mark it unverified in a comment.

## 1. The package contract

`sm/titles/xyz/__init__.py` provides these names. Copy the shape of `sm/titles/cok/__init__.py`:

| Name | What it is |
| --- | --- |
| `name` | The id string. |
| `commands` | Which of `test`, `run`, `serve` the title supports. |
| `automatic` | Decision kinds the title answers itself; usually empty. |
| `strict_choices`, `typed_inputs` | Set both true for a new title. |
| `presentation`, `ui_module` | Dotted paths to the screen module and the startup module (step 8). |
| `intake` | The intake module (imported at the top of the file). The browser server reads it as an attribute. |
| `require_content` | Usually `intake.require_folder`. |
| `create_game(player, slot, engines, directory)` | Returns your `Game`. Import it inside the function, so selecting a title stays cheap. |
| `Fault` | The exception for "not bound yet". Provide it through a module `__getattr__`, as `sm/titles/cok/__init__.py` does with `BindingRequired` from `sm/titles/cok/faults.py`. |
| `test()` | Runs the module checks; raise `SkipTest` when no game folder is configured. |
| `run_cli(command, arguments, local)` | Dispatches `test` and `run`. |

`python -m sm test --title xyz` calls `run_cli('test', ...)` after `require_content`, so it needs a game folder.

**Start with stubs.** `sm/titles/cok/faults.py` is short: copy it. `BindingRequired` subclasses `Halt` from `sm/titles/ssb/vm.py`, and `required` makes a function that raises it with a clear message. A half-built title then stops on an honest error, not a wrong answer.

## 2. Intake: which copies are supported

Copy `sm/titles/cok/intake.py` as it stands, and write your own `supported_versions.json` beside it (`sm/titles/cok/supported_versions.json` is the example). Change `ENV`, `HELP`, the messages and the settings file name. The server and launcher call these names, so keep them all:

`VERSION`, `ENV` (the environment variable that overrides the folder), `DataError` (imported from `sm/files.py`), `_active`, `catalog`, `config_path`, `configured`, `remember`, `inspect_folder`, `require_folder`.

`config_path` must give your title its own file name so titles do not overwrite each other's settings (`cok-intake.json` in the example).

`supported_versions.json` has this shape, and holds no game data:

```json
{"versions": [{"id": "gog", "label": "Store edition", "files": {"GAME.EXE": {"size": 123, "sha256": "..."}}}],
 "missing": "What to tell a player whose copy does not match."}
```

Generate the sizes and hashes with a throwaway script from your own copy. Then set your `ENV` variable to the game folder and run `python -m sm test --title xyz`: the first thing it does is verify the folder.

## 3. Tables from the game's own executable

`sm/titles/cok/data.py` (`Assets`) unpacks the resident program, then reads tables through `sm/titles/cok/tables.json`. Each entry is a location and a fingerprint, never the values:

```json
"classMin": {"shape": [17, 6], "format": "B", "size": 102, "sha256": "...", "offset": 63551}
```

To add a table, find its declaration in your reference, build the expected bytes in a scratch script outside the repository, search the unpacked executable for that pattern, and record the offset, size and hash. `Assets.table` then refuses to run on a mismatch. Strings work the same way: `part` and `text` in `sm/titles/cok/menu.py` read them from `sm/titles/cok/menu_layout.json`.

## 4. Records and saves

`sm/titles/cok/records.py` declares the disk layouts over `Record` from `sm/rec.py`: named fields, exact sizes, a lossless round trip. `sm/titles/cok/save.py` loads and writes the save container. Add up each candidate record's field widths against a real file before trusting its name: a reference can declare several similar records (Curse's `TCharRecord` is a 285-byte import shape; its saved record is `TCreature`, 422 bytes). Sidecar extensions differ by title too: Champions `.STF`/`.SFX`, Curse `.SWG`/`.FX`. `sm/titles/cok/rules.py` turns a disk record into a live `Char` and recalculates the derived numbers. Check it against the game's own starter saves, field by field: `sm/titles/cok/_rules_test.py` is the pattern.

## 5. The Game and its bindings

`sm/titles/cok/menu.py` subclasses the retained host as `Game`. The two dataclasses in `sm/pascal.py` hand the shared engine everything title-specific:

- `HostBinding`: `state`, `vm`, `geo`, `load`, `restore`, `root`, `initialize`, `finished`.
- `VMBinding`: `records`, `resident`, `wrapped_text`, `character`, `read_character`, `write_character`, `icons`, `service`.

They hold providers, never game state. `Game.service` routes a service call by unit name, and `Game.play` runs the main menu, then the adventure.

## 6. The zone scripts

`sm/titles/cok/town.py` binds the script interpreter to your layouts: `read_character` and `write_character` map script memory addresses to record fields; `Geo` is the 3D map; `VM` subclasses the shared interpreter for opcodes that differ; `wrapped_text`, `finished`, `play` and `service` finish the host. Bind only what your scripts use, and let `Fault` name the rest.

## 7. Services, one module each

A service is a module taking `game`: state is `game.s`, questions go through `game.ask`, and the result is a changed `State`. Dispatch happens in `Game.service` and `service` in `sm/titles/cok/town.py`. In the worked example, all under `sm/titles/cok/`:

| Module | Service |
| --- | --- |
| `creation.py` | Main menu, character creation, roster, save and load |
| `training.py` | Training, promotion, modify |
| `camp.py` | Camp, memorize, rest, fix |
| `alter.py` | Party order, speed, difficulty |
| `shop.py`, `temple.py` | Buying, selling, money, cures |
| `inventory.py` | The character sheet and item actions |
| `magic.py`, `effects.py` | Spells; timed effects and their handlers |

Port one at a time, and give each a sibling `_<module>_test.py` with `def test()`. Add new modules to the list in your `test()`.

The strongest check of a service is the original itself. `herdr/tools/route_b/` runs the game headless from Python: drive it through its own keys with the same seed, then compare its files or memory with yours (`herdr/tools/cok_oracle.py` is the worked example). RandSeed's address is per title (`seed_rva` in `herdr/tools/route_b/titles/`), and menu keys differ too: Curse's lists move with Home and End.

## 8. The screen

`presentation` names a module with the contract in [MOD_A_SCREEN.md](MOD_A_SCREEN.md); `ui_module` names a package with `START_SLOTS`, `SAVE_SLOTS`, `start_session` and `check`, as in `sm/titles/cok/ui/__init__.py`. Then `python -m sm.ui --web --title xyz` opens it.

The first screen module can be the main menu alone: `sm/titles/coab/ui/screen.py` is the minimum, and its `Assets` is empty because `render` reads `session.game.assets`. Frame drawing is per title: the border tables, symbol set and draw order all differ, so compare your first frame with the original under `herdr/tools/route_b/` pixel by pixel.

## 9. Checks and shipping

- `python -m sm test`: the engine's own suite.
- `python -B herdr/tools/cok_check.py` with the title's environment variable set: every module test of the worked example, one line each. Copy it for your title.
- `python -B herdr/tools/source_guard.py`: must print 0 hits. Run it from a full checkout, not a git worktree, or it cannot find the reference clones and reports 0 hits having checked nothing.
- `python -m sm.release` fails on any file under `sm/` that `sm/release_manifest.json` does not list. That applies from the first file of a new package. Add your package to `files` when it ships, or to `excluded` until then. Listed files are scanned for trademarks: use a title's name only where `allowed_phrases` permits it.
- To list a title in the Windows app, add it to `herdr/tools/release/titles.json`; `hidden` keeps it to the source tree.
