# flow-diagrams skill

A Claude Code skill that draws flow diagrams as Excalidraw files in my hand-drawn house style:
a neat professional look (no sloppiness, Nunito font, single ink colour), elbow arrows with labels,
boxes with a heading plus a short description, nested sub-parts, dotted lines for parallel
alternatives, and red only for review notes.

## Install on a machine

```bash
git clone https://github.com/TejasKashyap7/flow-diagrams-skill.git ~/Documents/skills/flow-diagrams-skill
mkdir -p ~/.claude/skills
ln -s ~/Documents/skills/flow-diagrams-skill ~/.claude/skills/flow-diagrams
```

To update later, run `git -C ~/Documents/skills/flow-diagrams-skill pull`.

Requirements: Python 3. The PNG preview also needs Playwright:
`pip install playwright && playwright install chromium`.

## Layout

- `SKILL.md`: the style rules and the workflow Claude follows
- `references/spec-format.md`: the JSON spec Claude writes for each diagram
- `scripts/build_flow.py`: spec → `.excalidraw` (layout, elbow-arrow routing, style check, `--copy` to the clipboard)
- `scripts/render_flow.py`: `.excalidraw` → PNG preview (dark mode)
