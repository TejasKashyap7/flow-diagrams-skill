# Flow spec format

The spec is a JSON file (`<name>.flow.json`) that says **what** is in the diagram.
`scripts/build_flow.py` decides **where** everything goes and writes the `.excalidraw`.

## Top level

Use either `sections` (one or more big titled frames side by side) or plain `nodes`.

```json
{
  "sections": [ { "id": "sr", "title": "Speech Recognition", "nodes": [ ... ] } ],
  "edges": [ ... ],
  "notes": [ ... ]
}
```

```json
{
  "title": "Optional big title above the flow",
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

Use one section per major subsystem. A small flow doesn't need sections.

## Box (node)

| field      | meaning |
|------------|---------|
| `id`       | unique, short, code-like (`vad`, `isSpeech`) — edges refer to it |
| `title`    | the heading. Decisions end with ` ?` ("Hangover ?") |
| `desc`     | short description: one or two lines on what it is. `\n` for line breaks; code-like lines (with `=`, `{`, `;`, `->`, or indented) are kept unwrapped |
| `children` | nested sub-parts drawn **inside** this box |
| `dashed`   | `true` for a dashed outline (used for nested sub-parts and groups of counters/state) |
| `layout`   | for a box with children: `"row"` (side by side, default when there are no arrows between them), `"column"` (stacked), `"flow"` (arrange by arrows) |
| `rank`     | force the column (0 = leftmost) within its container |
| `row`      | force the order within its column (0 = top) |
| `wrap`     | description wrap width in px (default 300) |
| `width` / `height` | minimum size, rarely needed |

## Arrow (edge)

```json
{ "from": "vad", "to": "isSpeech", "label": "Output (0,1)", "style": "dotted" }
```

- `from` / `to`: any box id at any depth. A nested child can point to a box outside its parent.
  Never connect a box to its own parent. Being inside already shows that it belongs there.
- `label`: what flows along the arrow, or the condition (`True`, `No`, `Audio chunks`,
  `Only valid after isInSpeech = True`). `\n` splits a long label onto two lines.
- `style`:
  - `solid`: the main path (default)
  - `dotted`: parallel alternatives. Use it when one step fans out into cases that exist side by side
    (1 → 1.1 and 1 → 1.2) and only one of them carries on to the next step
  - `dashed`: conditional, optional, feedback or retry path ("only valid after…", "if it fails, retry")

All arrows come out as elbow arrows with one arrowhead at the end, attached to boxes at both ends.
Arrows that point backwards (to the left) are routed underneath as a loop.

## Note (red)

```json
{ "for": "isAssertive", "text": "Why do we need 2 separate thresholds?" }
```

A note is drawn in red just above the box. Red is only for review notes, open questions and TODOs,
never for the flow itself.

## Full example

```json
{
  "sections": [{
    "id": "sr", "title": "Speech Recognition",
    "nodes": [
      {"id": "audio", "title": "Audio", "desc": "Raw mic input, 48kHz stereo"},
      {"id": "pre", "title": "Pre Processing", "desc": "Turns raw audio into what the VAD expects.", "children": [
        {"id": "fmt", "title": "Format Conversion", "desc": "Stereo → mono, 48kHz → 16kHz", "dashed": true},
        {"id": "chunk", "title": "Chunking", "desc": "576-sample chunks = 32ms each", "dashed": true}
      ]},
      {"id": "vad", "title": "Silero VAD", "desc": "LSTM model. Outputs a speech probability 0 → 1"},
      {"id": "isSpeech", "title": "isSpeech ?", "desc": "isSpeech = vadProbability >= 0.50"},
      {"id": "isAssertive", "title": "isAssertive ?", "desc": "Louder speech used for barge-in."},
      {"id": "watch", "title": "Stop Watches", "desc": "Counts voiced and silent time."}
    ]
  }],
  "edges": [
    {"from": "audio", "to": "pre", "label": "Audio"},
    {"from": "fmt", "to": "chunk"},
    {"from": "pre", "to": "vad", "label": "Input (576 samples)"},
    {"from": "vad", "to": "isSpeech", "label": "Output (0,1)", "style": "dotted"},
    {"from": "vad", "to": "isAssertive", "label": "Output (0,1)", "style": "dotted"},
    {"from": "isSpeech", "to": "watch", "label": "True"},
    {"from": "isAssertive", "to": "watch", "label": "Only valid after\nisInSpeech = True", "style": "dashed"}
  ],
  "notes": [{"for": "isAssertive", "text": "Why do we need 2 separate thresholds?"}]
}
```
