---
name: flow-diagrams
description: Draw flow diagrams as Excalidraw files in Tejas's own hand-drawn house style — clean professional look (no sloppiness, Nunito font, single ink colour), elbow arrows with labels, boxes with a heading plus a short description, nested sub-parts, dotted lines for parallel alternatives and red only for review notes. Use this whenever the user asks for a flow, flowchart, pipeline, architecture, system or process diagram, wants to "draw", "map out", "visualise" or "explain with a diagram" how some code, service or process works, or mentions Excalidraw — even if they don't say "flow diagram" explicitly.
---

# Flow diagrams in Tejas's style

These diagrams are used in professional settings: to explain a system to a team or client
and to review a design. They must look **neat and polished**, as if drawn carefully by hand in
Excalidraw. They should not look sketchy or auto-generated. Every rule below comes from the user's
own hand-drawn diagrams and their explicit corrections.

## The style (what a finished diagram looks like)

**Appearance — neat above all**
- Sloppiness is always 0 ("architect"). Font is always **Nunito**. A sketchy look reads as
  unprofessional in front of a client.
- A single ink colour (`#1e1e1e`, which shows as light grey in dark mode), stroke width 2,
  rounded rectangles, no fills. The diagrams are viewed in dark mode.
- Sizes: section titles 36, box headings 20 (16 for nested parts), body text and labels 16.

**Boxes**
- Every box has a **heading**, then a **short description** saying what it is: one or two lines,
  a phrase or a sentence. Real values, variable names and a tiny bit of code are welcome
  (`576 samples`, `isSpeech = vadProbability >= 0.50`). Don't write paragraphs. If there's more to say,
  that's a sign the box has sub-parts.
- Decisions are ordinary boxes whose heading is a question, such as `isSpeech ?` or `Hangover ?`.
  Never use diamonds. The arrows leaving them carry the answers (`True` / `False`, `Yes` / `No`).

**Sub-parts: nested vs child boxes**
Anything with parts gets either nested boxes or child boxes. Choose by asking whether the parts
are pieces of this one thing, or steps the flow passes through.
- **Nest** them (dashed boxes inside the parent) when they are internal pieces or ingredients of the
  parent. The reader should see one component and what it's made of. Examples from the user:
  Pre Processing ⊃ Format Conversion, Chunking; isAssertive ? ⊃ RMS of Loudness, Barge-In
  Threshold; Stop Watches ⊃ Voiced Seconds, Silence Seconds; Response Check ⊃ Word Check,
  Is Agent Active ?. Nested parts can still have arrows between them (Format Conversion → Chunking)
  and can point to boxes outside the parent.
- Make **separate child boxes joined by arrows** when they are distinct stages that data moves
  through, such as Recording → Loudness Check → Transcription.

Big topics (whole subsystems) become **sections**: large frames with a centred title, placed
side by side. Arrows can go from a box in one section to a box in another.

**Arrows**
- Always **elbow arrows** (right angles). Each has one arrowhead at the end and is attached to a box at both ends.
- Put **text on arrows**: what flows along them (`Audio chunks`, `Input (576 samples)`) or the condition
  (`True`, `Only valid after isInSpeech = True`). Most arrows that carry data or a decision
  should have a label. Obvious "next step" arrows can go without.
- Line style has meaning:
  - **solid**: the main path.
  - **dotted**: parallel alternatives. Step 1 fans out to 1.1 and 1.2, which exist side by side, and only
    one of them carries on to step 2. (Silero VAD → isSpeech ? and → isAssertive ? are dotted.)
  - **dashed**: conditional, optional, feedback or retry paths ("only valid after…", "if it fails,
    flag is reversed and the model retries").

**Layout**
- Flow runs **left to right**, from the input (usually a small box such as "Audio" or "User request") to the output.
- Loop-backs go underneath, so they never cut through the main path.

**Red is the user's review voice**
Red text (`#e03131`) is only for review notes: open questions, concerns and TODOs
("Why do we need 2 separate thresholds?", "We have to remove this block"). Never use red for flow
elements. Add red notes when the user asks for review comments. You may also add one when you
spot a genuine issue worth flagging while reading the code. Keep them few and specific.

## How to make one

Don't hand-write Excalidraw JSON. Elbow-arrow bindings, label positions and text sizing are
easy to get subtly wrong, and those are exactly what make a diagram look sloppy. Write a small
spec instead and let the script lay it out.

1. **Understand the thing first.** Read the code, docs or the user's description until you can say,
   for each step, what goes in, what comes out, and what decides the path. Pull out the real
   names and numbers (function names, thresholds, sample sizes). They are what make the user's
   diagrams useful.
2. **Plan the structure** before writing JSON:
   - the sections (one per subsystem), or no sections for a small flow
   - the boxes in each section, in flow order, and which ones have sub-parts (nested or child boxes?)
   - the decisions (`… ?`) and their labelled branches
   - which fan-outs are parallel alternatives (dotted) and which paths are conditional or feedback (dashed)
3. **Write the spec** as `<name>.flow.json`. The format is in `references/spec-format.md`;
   read it the first time. Keep each `desc` to one or two lines.
4. **Build** it:
   ```bash
   python3 <skill-dir>/scripts/build_flow.py <name>.flow.json -o <name>.excalidraw
   ```
   The script lays out the columns and routes the elbow arrows. It also runs a style check (no sloppiness, Nunito,
   elbow arrows, bound ends, single ink colour). Use `--check file.excalidraw` to check any existing file.
5. **Look at it.** Render a PNG and view it with the Read tool:
   ```bash
   python3 <skill-dir>/scripts/render_flow.py <name>.excalidraw   # dark mode, writes <name>.png
   ```
   For a wide diagram, crop it into halves with PIL to check the details. Look for overlapping or
   crossing arrows, cramped labels, text spilling out of boxes, a box that is too wordy, and
   arrows routed the long way round. Fix the problem in the spec: reorder nodes, set `rank` or `row`, split a
   long description, or move a sub-part between nested and child. Then rebuild. One or two passes are normal.
6. **Hand it over** (see below).

## Where files go and how the user opens them

Everything stays **local**: never upload, publish or share the diagram to any online service
(no excalidraw.com share links, no live collaboration, no Artifacts). Save the `.flow.json`,
`.excalidraw` and `.png` together. Use a `flows/` folder in the current project unless the user names a
place, and give the full paths.

To open the diagram, the user can use either of these. Both stay in the browser and nothing is uploaded:
- **Paste into an existing canvas** (safest): run the build with `--copy`. It puts the diagram on the
  clipboard in Excalidraw's format. Then click the canvas at excalidraw.com and press Cmd+V.
  This adds the diagram next to what's already there.
- **Open the file**: excalidraw.com → menu → Open → choose the `.excalidraw` file. Warn the user that this
  **replaces** whatever is on their current excalidraw.com canvas. Their hand-drawn work lives only in
  that browser's storage, so they should save it first (menu → Save to…) or use the paste route.

Don't operate the user's Excalidraw tab yourself unless they ask. If you do, never clear or
overwrite their existing canvas.

## Editing an existing diagram

If the user wants changes to a diagram made with this skill, edit its `.flow.json` and rebuild.
Don't patch the `.excalidraw` by hand. If they only have an `.excalidraw` file (for example one they drew), you
can still check it with `--check`. To restyle or extend one, recreate its content as a spec.
