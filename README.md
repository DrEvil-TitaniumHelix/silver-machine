# SilverMachine

plays the SSI Gold Box games from your own copy.

Fan project; not affiliated with or endorsed by Wizards of the Coast, SSI or their successors. Requires your own copy of the games.

Built with AI: most of this code was written by AI coding agents directed by DrEvil; see the private development notes for method.

**Alpha 0.1.3 — Windows x64.** Compatible with Secret of the Silver Blades (PC/DOS): GOG and Collector's CD.

Download `SilverMachine-0.1.3-windows-x64.zip`, extract the complete folder, and double-click **SilverMachine.exe**. Python is included; no installation or commands are needed. The SilverMachine title list opens in your browser. Choose **Play**.

Use **Browse** to navigate folders inside the page, or type the folder containing your copy's `ITEMS` and data files. You can also drag your game folder onto **SilverMachine.exe** before starting. Dragging a text path into the field works too; browsers do not expose Explorer folder paths to a web page. The engine checks the same supported editions and rejects other data. Your original files stay read only.

Use **Game folder** to change your copy; quit and reopen to apply a change to an active game. Supported: the GOG release (recommended, buy it) or the original Collector's CD. We recommend the GOG releases as the supported way to own the games: Forgotten Realms: The Archives Collection One and Two, and Dungeons & Dragons: Krynn Series.

Without an existing save A or autosave, the party menu opens. Create and save each character, use **Add** to put them in the party, then choose **Begin**. Created characters and saved games go into the save location; your game-data folder is read only.

Click the game for keyboard control; use arrow keys to move, F2 for the map and **F10 → Quit** to close the game. Closing only the browser tab leaves the game running. The launcher chooses a free local port each time.

The Windows app keeps saves in `%LOCALAPPDATA%/SilverMachine/ssb/saves` and settings in `%LOCALAPPDATA%/SilverMachine/ssb/config`. Replace the extracted app folder to update; your progress stays in the player data folder. Keep that data folder when reinstalling. Other titles can be added to the same SilverMachine app in future releases.

The **Plus** tile opens Journal, maps, help and display options. When the game cites a journal entry, its on-screen link opens Journal at that entry. Your GOG `Adventurers Journal.pdf` is read in place using the browser's PDF viewer; CD owners are directed to their printed journal. Journal briefings, conversation history and your notes are kept beside your saves.

Report problems using [the alpha bug-report template](docs/ALPHA_BUG_REPORT.md), including the version and build shown on screen.

Developers using the source tree can still run `python -m sm.ui --web` with Python 3.12 or newer. Source mode retains its existing save and config locations; `SM_SECRET` overrides the saved game folder. Source releases include tests: set it to your verified copy and run `python -m sm test`. Checks requiring excluded developer routes or installed save fixtures print `SKIP`; the pristine new-party check runs without those fixtures. `python -m sm.release` validates the source manifest and creates `local/silvermachine-alpha-0.1.3.zip`. The Windows build recipe is `herdr/tools/release/package.py` in the development workspace.

0.1.3: bundled Python and one-click Windows launcher, SilverMachine title list, Browse without Tk, and saves/settings preserved outside the app folder.

Code licensed under MIT (see LICENSE); this covers our code only, never game data.

Reference: the Brazen Crows / talonius source reconstructions (https://github.com/talonius) were read as a reference only; no code from them is used.
