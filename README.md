# SilverMachine

[![Get it on RecompLauncher](https://recomplauncher.com/assets/press/launcher/badge-dark.svg)](https://recomplauncher.com/game/silver-machine) [![Verified developer on RecompStore](https://recompstore.com/assets/press/verified-dark.svg)](https://recompstore.com/dev/drevil-titaniumhelix)

plays the SSI Gold Box games from your own copy.

Fan project; not affiliated with or endorsed by Wizards of the Coast, SSI or their successors. Requires your own copy of the games.

Built with AI. Almost no AI content: the game's content and visuals come from the player's own copy of the original.

**Beta 0.1.9 — Windows x64.** Plays Secret of the Silver Blades (PC/DOS) from the GOG release or the original Collector's CD. Compatible with Champions of Krynn (PC/DOS): GOG. Other titles will join the same app in later releases.

## Play

1. From RecompLauncher or Quiver: install, point the launcher at your game folder when it asks, press **Play**; the game opens directly. Without a launcher: download `SilverMachine-0.1.9-windows-x64.zip`, extract the whole folder, and double-click **SilverMachine.exe**. Nothing to install. The title list opens in your browser; choose **Play**.
2. Without a launcher, point it at your game folder: use **Browse**, type the folder path, or drag your game folder onto **SilverMachine.exe** (the game then opens directly). Your original files are only read, never changed.
3. The first time, the party menu opens. Create and save your characters, **Add** them to the party, then choose **Begin**. If you already have a save A or an autosave, the game continues from it.

Supported copies: the GOG release (recommended; Secret of the Silver Blades is in *Forgotten Realms: The Archives - Collection Two*) or the original Collector's CD. Other data is refused. **Game folder** on the title page changes your copy; reopen the game to apply it.

## Controls

Click the game to give it the keyboard. Arrow keys move; **F2** shows the area map; **F10** opens Save, Load, Quit and Resume. Quit from that menu to close the game: closing the browser tab alone leaves it running.

Your saves and settings live outside the app folder, so you can replace the app folder with a newer version and keep your progress.

## Plus

The **Plus** tile opens the Journal, the full area map, help, the rules tables, a bug report form, the picture gallery and the guide. When the game cites a journal entry, its on-screen link opens the Journal at that entry. GOG owners read their `Adventurers Journal.pdf` in place; CD owners use their printed journal.

Report problems with [the bug-report template](docs/ALPHA_BUG_REPORT.md), including the version and build shown on screen.

## Fork it

SilverMachine is built to be forked and changed: the rules, the screens and each service (shops, camp, training) are separate modules, and every run can be replayed and compared decision by decision. Start with [CONTRIBUTING.md](CONTRIBUTING.md). [docs/ADD_A_TITLE.md](docs/ADD_A_TITLE.md) shows how to add a title, [docs/MOD_A_SCREEN.md](docs/MOD_A_SCREEN.md) how to change one screen or service, and [docs/DECISIONS.md](docs/DECISIONS.md) how the game and its players talk. A fork still needs each player's own copy of the games; no game data ships here.

## Licence and credits

Code licensed under MIT (see LICENSE); this covers our code only, never game data.

Reference: the Brazen Crows / talonius source reconstructions (https://github.com/talonius) were read as a reference only; no code from them is used.
