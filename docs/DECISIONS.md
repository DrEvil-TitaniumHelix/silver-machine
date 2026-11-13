# Decisions: how the game talks to a player

Everything a player can do in SilverMachine is a **decision**. The simulation stops, asks one question from a closed list, and carries on with the answer. A browser, a test script and an auto-player all answer the same questions. There is no other way in.

## The call

Game code asks with `game.ask(kind, options, **info)` (`sm/titles/ssb/host.py`, inherited by every title's `Game`).

| Argument | Meaning |
| --- | --- |
| `kind` | A string from a closed list, such as `CREATE_RACE` or `SHOP_MENU`. |
| `options` | A tuple of labels, or `None` when the answer is typed rather than picked. |
| `info` | Anything the screen needs. Only `int` and `str` values reach a `Session` client. |

**What `ask` returns:** the index into `options`, or, when `options` is `None`, the value itself (a string or a number). The string and number kinds are checked by the code that asks: see `read_name` in `sm/titles/cok/creation.py`. Two reserved kinds, `NUMBER` (0 to 65535) and `STRING` (up to 40 characters), are also checked by the transport.

A helper usually wraps this. `choose` in `sm/titles/cok/creation.py` appends an Exit option and returns the index or `None`; `pick` in `sm/titles/cok/shop.py` also carries a pending bottom-line message.

## Where kinds are declared

Per title, per module, as a closed `Enum` named `Kind`, so a typo fails at import. In the worked example, `sm/titles/cok/`:

`creation.py` (main menu, character creation), `camp.py`, `shop.py`, `temple.py`, `training.py`, `inventory.py`, `alter.py`, `magic.py`.

To see every kind a title can ask, read those enums. Script-level kinds (menus inside the zone scripts) come from the interpreter in `sm/titles/ssb/vm.py`.

## Driving it: `Session`

`sm/engine.py` runs the game on a worker thread, one pending decision at a time.

```python
from sm.engine import Session
from sm.titles import cok

session = Session(profile=cok, slot=None, directory=folder, auto_resolve=False)
for _ in range(5):              # a real player loops until session.decision is None
    d = session.decision        # {'kind', 'options', 'info', 'i', 'hash'}
    print(d['kind'], d['options'], d['hash'])
    session.step(0)             # the option index, or a typed value
session.close()
```

- `session.step(answer)` validates the answer and returns the next decision, or `None` when the game ended.
- A profile lists kinds it can answer by itself in `automatic`, with `resolve_decision`. Pass `auto_resolve=False` to see them.
- `python -m sm serve` exposes the same loop as JSON lines on stdin and stdout, and `play` in `sm/engine.py` runs a policy function headlessly.

## The state hash

Each decision carries `hash`, from `game.state_hash()` (`hash` in `sm/titles/ssb/state.py`). It covers the memory regions, every party and monster record with items and effects, position, modes, the random seed, everything in the `s.g` dictionary and the script interpreter's position.

Two rules follow, and everything else depends on them:

1. **Anything a later decision can depend on lives in `State`.** Use `s.g` for small engine flags. A value kept on the `game` object is not hashed, so keep only what cannot change a decision there.
2. **Randomness comes only from `s.random`.** No clock, no `random` module, no dictionary order.

Rendering, paging and selection never change the hash.

## Replay

Same seed and same answers give the same hash at every decision. `game.trace` records them as `(index, kind, dataset, block, at, hash, choice)`, and `Replay` in `sm/replay.py` compares two runs and names the first decision that differs. Every service test here runs twice from fresh temporary folders and asserts the hashes match: see `_shop_test.py` in `sm/titles/cok/`.

A divergence is always a bug in the state rules above, and the first differing decision is where to look.
