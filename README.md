# SilverMachine

plays the SSI Gold Box games from your own copy.

Fan project; not affiliated with or endorsed by Wizards of the Coast, SSI or their successors. Requires your own copy of the games.

**Alpha 0.1.** PC (DOS) editions only. Supported: the GOG release (recommended, buy it) or the original Collector's CD. We recommend the GOG releases as the supported way to own the games: Forgotten Realms: The Archives Collection One and Two, and Dungeons & Dragons: Krynn Series.

With Python 3.12 or newer installed, open a terminal in this folder and run:

```text
python -m sm.ui --web
```

Use **Browse** or type the folder containing your copy's `ITEMS` and data files on the web page. Browse opens a native folder dialog; without Python's Tk support, type the path instead. The engine verifies it before starting. Use **Game folder** to change it later; restart the server to apply a change to an active game. `SM_SECRET` overrides the saved folder. On Windows, settings live in `%APPDATA%/runtime-data/intake.json`.

Without an existing save A or autosave, the party menu opens. Create and save each character, use **Add** to put them in the party, then choose **Begin**. Created characters and saved games go into the save location; your game-data folder is read only.

Click the game for keyboard control; use arrow keys to move, F2 for the map and F10 to save, load or quit. Ctrl+C stops the server. Saves currently live in `local/saves` inside this folder; keep that directory when updating.

The **Plus** tile opens Journal, maps, help and display options. When the game cites a journal entry, its on-screen link opens Journal at that entry. Your GOG `Adventurers Journal.pdf` is read in place using the browser's PDF viewer; CD owners are directed to their printed journal. Journal briefings, conversation history and your notes are kept beside your saves.

Report problems using [the alpha bug-report template](docs/ALPHA_BUG_REPORT.md), including the version and build shown on screen.

For a release review, run `python -m sm.release`. It checks `sm/release_manifest.json` and builds `local/silvermachine-alpha-0.1.zip`. The cut includes tests: set `SM_SECRET` to your verified copy and run `python -m sm test`. Checks requiring excluded developer routes or installed save fixtures print `SKIP` with the missing dependency; the pristine new-party check runs without those fixtures.

Code licensed under MIT (see LICENSE); this covers our code only, never game data.
