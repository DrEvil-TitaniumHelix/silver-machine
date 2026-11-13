# Contributing

SilverMachine is meant to be forked and changed. Fork it, change what you like, and send back what others could use.

## Start here

- [docs/DECISIONS.md](docs/DECISIONS.md): how the game talks to a player, state hash and replay.
- [docs/ADD_A_TITLE.md](docs/ADD_A_TITLE.md): add a title.
- [docs/MOD_A_SCREEN.md](docs/MOD_A_SCREEN.md): change one screen or one service.

Python 3.12, standard library only.

## Before a pull request

1. `python -m sm test` passes.
2. The check for what you touched passes, with your game folder set: each title's modules have a `_<module>_test.py`.
3. `python -B docs/_check_links.py` passes if you changed these docs.

## Three rules

- **No original bytes.** Never commit game files, decompressed data, pictures, sound, saves or screenshots of game art. Sizes, offsets and SHA-256 hashes are fine.
- **No copied lines.** Decompiled or reconstructed source may be read to learn what a game does. Write your own code. `herdr/tools/source_guard.py` enforces this where the reference clones are available.
- **No guessed game facts.** Take them from a reference or the game's own bytes, or mark them unverified in a comment.

Keep the product name separate from game names: see the `allowed_phrases` in `sm/release_manifest.json`.

## What a good pull request has

One change, its check, and a sentence saying what a player now sees. If the change moves replay hashes, say why. Code is under the MIT licence (`LICENSE`), and covers our code only, never game data.
