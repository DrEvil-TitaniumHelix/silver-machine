# Death Knights of Krynn profile contract

**Plays from the title to the ending. Each of the 69 play paths has been run against the original and was equal to its end; one continuous run of our game went from the supplied party past the ending to Dave's challenge (its last fight was not won by the auto-player). Release checks are still open (last row).**

| Title responsibility | Death Knights evidence / state |
| --- | --- |
| External edition and content root | `intake.py`: 53 file fingerprints of the GOG copy (`supported_versions.json`); `SM_DKK` or the folder page |
| Resident tables | `data.py`, `tables.json`: 543 parts of the player's unpacked `START.EXE` located and hashed (menu words, prompts, names, rule and spell tables), values read in memory; a differing byte stops the load. The menu parts live here too, so there is no separate `menu_layout.json` |
| Character/item/effect/save layouts | `records.py`: character 216 bytes, spells 220, item 63, effect 9, saved game 2913. `save.py`, `save_chars.py`, `save_start.py`, `save_vault.py`: slots A..J, imported characters, the vault. A game saved by the original loads in ours and plays on; ours loads its own saves from every kit place |
| Scripts and exploration | `ecl.py` (script decoder), `town.py` (script engine and host, `Geo`), `world_explore.py` (the exploring menu Move, Area, Cast, View, Encamp, Search, Look; the overland menu Move, Encamp; steps and turns), `world_vault.py` |
| Party, rules and creation | `menu.py` (party menu and frames), `creation.py` (creation, training, Modify), `rules.py` (character recalculation, movement, spell slots) |
| Effects | `effects.py`, `effects_ability.py`, `effects_area.py`, `effects_handlers.py` |
| Magic | `magic.py` (casting, ranges, durations), `magic_lists.py` (spell lists, scrolls), `magic_study.py` (memorize, scribe) |
| Combat | `combat.py`: placement, initiative, movement, attacks, the computer's turns, Quick, missiles, morale, treasure |
| Services | `shop.py`, `temple.py`, `camp.py`, `inventory.py`, `alter.py`, `services_alter.py` |
| Presentation | `ui/screen.py` (the Champions screen code with Death Knights replacements), `ui/title.py` (title pictures, credits, the demo); `python -m sm.ui --web --title dkk` |
| Plus | `ui/plus.py`: Effect time and Sound options, the area map of the current grid, help written for the Death Knights keys. Journal: `journal_lock.json` holds the booklet's 65 entries (1 to 12, 14 to 66; the booklet has no 13), sealed; an entry opens only with the player's own `ECL2.DAX`, and the player's `Journal.pdf` is one link away |
| Verification | 69 play paths (a key list from a named start, fixed seed), each run equal to the original to its end once at a master after its last change, at most two copies of the original at once (`herdr/compare/dkk/PATHS.md`, `herdr/tools/dkk_compare.py`); spot-check kit of 29 places and 96 saves (`herdr/tools/dkk_kit.py`) |
| Open | The release list in `herdr/compare/dkk/FINISH.md`: Lightning Bolt drawn per stretch, the quit met near Lord Soth, a new player's first hour, kit cards, the fights ledger, reviews, the release build. Not on the finished list: sound, the mouse, the joystick |

Check: `python -B -m sm test --title dkk`, `python -B herdr/tools/dkk_check.py`.

Reference credit: Brazen Crows / talonius, **reference only, no code**.
