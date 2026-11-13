# PNG mods

On Plus, choose **Look → VGA**, then your **Mods folder**. Original ignores mods.
Nothing is bundled; PNG paths are relative to that folder or absolute paths to
your existing art. `mods.json` is a list:

```json
[
  {"kind": "icon", "slot": 0, "png": "knight.png"},
  {"kind": "icon", "head": 2, "body": 2, "png": "priestess.png"},
  {"file": "PIC4", "id": 6, "png": "dragon-portrait.png"},
  {"file": "CPIC1", "id": 6, "png": "dragon-ready.png"},
  {"file": "CPIC1", "id": 134, "png": "dragon-action.png"}
]
```

**One icon = one complete figure**, head and body together. Use either a
zero-based party `slot` (0–5 in the current party order), or the base `head`
and `body` CHEAD/CBODY ids (0–63, without size/pose offsets). Slot overrides
the pair. Equipment Icons uses the displayed body id for pair matching.
One figure is used for both poses and mirrors with native facing. Each key
must be unique. Separate CHEAD/CBODY strip replacements are rejected.

Combat figures render in a browser overlay at the displayed canvas resolution:
at 3×, a single-tile party figure fits a **72×102** cell, with its feet on the
native tile baseline and ten native pixels of extra headroom. Transparent outer
margins are trimmed; proportions and the whole figure are preserved. The browser
samples directly from the source PNG, never through a 24-pixel intermediate.
Native terrain, icons and effects retain their draw order and board clipping.
Movement, facing, camera position and death visibility come from the same scene
as the native frame. Mods off or Original leaves the overlay empty. The underlying
320×200 combat frame and its packet bytes remain unchanged. Native screenshots
contain that underlying frame; capture the browser to include display overlays.

Other picture keys use **container basename + decimal record id + optional
frame**. `PIC4` and `PIC4.DAX` are equivalent; names are case-insensitive. Ids and
frames are 0–255; `frame` defaults to 0. Use the actual numbered container, not
`PIC`. Plus Gallery shows picture ids. CPIC combat records use the full-figure
overlay too; ready/action ids are commonly 128 apart. Non-combat pictures still
fit their native content rectangle. Neither path quantizes colours or applies
the character's EGA recolouring to a replacement.

Use **real PNG alpha**, preferably RGBA. Global colour keys (`transparent`) are
rejected because they punched holes in dark armour and robes. For opaque legacy
art only, this explicitly temporary stopgap removes border-connected background:

```json
{"kind": "icon", "slot": 0, "png": "knight_icon.png",
 "edge_background": "#000000", "edge_tolerance": 8}
```

The four-connected flood starts at the image border; enclosed matching colours
stay opaque. `edge_tolerance` is the maximum difference per RGB channel, 0–32,
default 0. The art-pack demo uses 8 for near-black background noise. Dark details
connected to the background can still be affected: this is a stopgap until the
art is re-exported with alpha. Without `edge_background`, source alpha is retained
unchanged, including partial transparency. No source PNG is modified or copied.

Supported PNGs are 8-bit, non-interlaced RGB, RGBA, greyscale, grey-alpha or
indexed: at most 2048 pixels per side, one million pixels total and 16 MiB.
Decoding and optional edge flood use server-side stdlib code; the browser
composes the resulting RGBA images only after they are decoded, with the matching
frame snapshot. Missing/unreadable art falls back to native icons with a Plus
status message. Apply the folder again after editing images/index; Clear removes
the preference. SSB VGA uses SSB chrome unless your own Dark Queen copy is configured.
