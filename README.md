# SilverMachine

[![Get it on RecompLauncher](https://recomplauncher.com/assets/press/launcher/badge-dark.svg)](https://recomplauncher.com/game/silver-machine) [![Verified developer on RecompStore](https://recompstore.com/assets/press/verified-dark.svg)](https://recompstore.com/dev/drevil-titaniumhelix)

plays the SSI Gold Box games from your own copy.

Fan project; not affiliated with or endorsed by Wizards of the Coast, SSI or their successors. Requires your own copy of the games.

Built with AI. Almost no AI content: the game's content and visuals come from the player's own copy of the original.

**Beta 0.1.12 — Windows x64.** Plays Secret of the Silver Blades (PC/DOS) from the GOG release or the original Collector's CD. Compatible with Champions of Krynn (PC/DOS): GOG. Compatible with Death Knights of Krynn (PC/DOS): GOG. Other titles will join the same app in later releases.

## Play

You need a 64-bit Windows PC and your own copy of a game. Point SilverMachine at the game's own folder:

- **Silver Blades**: the folder that holds `START.EXE` (GOG) or `ST.EXE` (Collector's CD, the `WIZWORKS\SECRET` folder).
- **Champions** and **Death Knights** (GOG's Krynn Series): each game's own folder, the one that holds `START.EXE` and the `.DAX` files.

GOG usually installs a game under `C:\Program Files (x86)\GOG Galaxy\Games\` (GOG Galaxy) or `C:\GOG Games\` (offline installer). Pick the game's folder, not the folder above it.

Four ways to start:

1. **RecompLauncher**: install SilverMachine; each game has its own tile. On the game's page, pick your folder in that game's field (leave the others empty) and press **Play**: the game opens directly. Leave the field empty and the game asks for the folder in its first screen.
2. **Quiver**: install SilverMachine and start it. The title list opens in your browser; choose **Play** on your game. The first time, the game's first screen asks for your game folder: **Browse** opens the Windows folder dialog, or type the path.
3. **The zip**: download `SilverMachine-0.1.12-windows-x64.zip` and extract it (right-click, **Extract All**); in the extracted folder, open `SilverMachine-0.1.12-windows-x64` and double-click **SilverMachine.exe**. Nothing to install. The title list opens in your browser; choose **Play**, then pick your game folder the first time.
4. **Drop the folder**: drag your game folder onto **SilverMachine.exe** and the game that folder holds opens directly. If the title list opens instead, SilverMachine did not recognise the folder: choose **Play** on your game and pick the folder there.

The first time, the party menu opens. Create and save your characters, **Add** them to the party, then choose **Begin**.

If the game refuses your folder, the message says why:

- *This folder does not match a supported ...*: this is not the game's folder (often the folder above it, or another game's). Choose the folder that holds `START.EXE` (`ST.EXE` on the Collector's CD). For Silver Blades it can also mean an incomplete, changed or other copy: reinstall it, or use a supported copy.
- *... is missing ...* (Champions, Death Knights): the copy is incomplete, or this is the folder of another game of the same family, such as Silver Blades or the other Krynn game (they share many file names). Check that you picked this game's own folder; otherwise choose the complete game folder, or reinstall the game.
- *... changed or damaged* (Champions, Death Knights): the files differ from the GOG edition: changed or damaged, or the copy is not the GOG edition (these two games accept only the GOG release). Verify or reinstall your GOG copy, then choose it again.
- *Cannot use this folder*: the folder could not be read; the message gives the reason.

Supported copies: the GOG release (recommended; Secret of the Silver Blades is in *Forgotten Realms: The Archives - Collection Two*) or the original Collector's CD. The Collector's CD is for Silver Blades only; Champions and Death Knights accept the GOG release only. Other data is refused. **Game folder** on the title page changes your copy; reopen the game to apply it.

Your saves and settings live in `%LOCALAPPDATA%\SilverMachine`, one folder per game (`ssb`, `cok`, `dkk`), outside the app folder: replace the app folder with a newer version and your progress stays. In RecompLauncher the **Saves** button opens that folder. Your game folder is only read, never changed.

## Controls

Click the game to give it the keyboard. Arrow keys move; **Area** on the game's menu shows the area map; **F10** opens the save and quit menu. Quit from that menu, or close the game's window: the program ends a few seconds after its last window closes.

## Plus

The **Plus** tile opens the Journal, the area map and help; Silver Blades adds the rules tables, a bug report form, the picture gallery and the guide. The Journal lists each journal entry the game has cited and shows its text from your copy, and opens the journal PDF in your game folder (`Adventurers Journal.pdf` for Silver Blades, `Journal.pdf` for Champions and Death Knights). Collector's CD owners use their printed journal.

Report problems with [the bug-report template](docs/ALPHA_BUG_REPORT.md), including the version and build shown on screen.

## Fork it

SilverMachine is built to be forked and changed: the rules, the screens and each service (shops, camp, training) are separate modules, and every run can be replayed and compared decision by decision. Start with [CONTRIBUTING.md](CONTRIBUTING.md). [docs/ADD_A_TITLE.md](docs/ADD_A_TITLE.md) shows how to add a title, [docs/MOD_A_SCREEN.md](docs/MOD_A_SCREEN.md) how to change one screen or service, and [docs/DECISIONS.md](docs/DECISIONS.md) how the game and its players talk. A fork still needs each player's own copy of the games; no game data ships here.

## Licence and credits

Code licensed under MIT (see LICENSE); this covers our code only, never game data.

Reference: the Brazen Crows / talonius source reconstructions (https://github.com/talonius) were read as a reference only; no code from them is used.
