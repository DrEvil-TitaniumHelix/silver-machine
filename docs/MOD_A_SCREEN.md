# Change one screen or one service

Screens and services are separate from each other and from the engine, so a change to one touches one file. Read [DECISIONS.md](DECISIONS.md) first.

## The screen contract

The browser server, `sm/ui/web.py`, knows nothing about any title. It imports the module named by the profile's `presentation` and uses these names. `sm/titles/cok/ui/screen.py` is the worked example.

| Name | Used for |
| --- | --- |
| `Controller(session, save_root=..., presentation=...)` | Turns keys into game answers. |
| `Controller.session` | The `Session` it drives. |
| `Controller.key(keysym, char)` | One key press. |
| `Controller.quit_requested` | True ends the server. |
| `Controller.remember`, `Controller.autosave`, `Controller.set_effect_scale` | Called by the server; they can do nothing. |
| `Assets()` | Decodes the player's art in memory. |
| `render(controller, assets, elapsed)` | Returns a frame of palette indices. |
| `layout(controller)` | A dictionary with `revision` and the clickable regions. |
| `PALETTE`, `LOCAL` | The colours, and a folder for logs. |

Optional, used when present: `Controller.apply_plus`, a frame's `packet`, `FRAME_FORMAT`. The server also sets `decision_observer` and `autosave_enabled` on the controller.

**To change how one screen looks,** edit the drawing function for it in your title's `screen.py`: `draw_frame`, `draw_party`, `draw_view` and `draw_picture` in the example, with `render` choosing between them. To change what a key does, edit `Controller.key`. Neither can affect the simulation: only a committed answer through `session.step` does. If replay changes after a screen edit, the edit reached into game state and should not have.

Run a title's screens with `python -m sm.ui --web --title cok`.

## Art and overlays

Replacing pictures needs no code: see [the mods guide](../sm/ui/MODS.md) (`sm/ui/MODS.md`). The Plus page settings live in `sm/ui/plus.py`.

## Replace or change a service

A service is one module (the table is in [ADD_A_TITLE.md](ADD_A_TITLE.md)). Say you want different shop prices: only `price_of` in `sm/titles/cok/shop.py` changes.

1. Keep the module's public names. Other modules call `run` and helpers such as `coins` and `pick`; check with a search before renaming.
2. Keep state in `State` and random numbers in `s.random`, as [DECISIONS.md](DECISIONS.md) requires.
3. Run its check: `python -I -B sm/titles/cok/_shop_test.py <game folder>`.

**What replay tells you.** A service you did not change must give identical hashes at every decision. A service you changed on purpose will differ from the first decision your change affects, and every earlier hash stays equal, which is how you confirm the change touched only what you meant. Update the test's expected values once you have read why they moved.

To swap a whole service, write a new module with the same `run(game)` and change the dispatch in `Game.service` or `service` in `sm/titles/cok/town.py`. A service you have not finished should raise the profile's `Fault` with a message naming what is missing, so a player gets an honest stop and not a wrong result.
