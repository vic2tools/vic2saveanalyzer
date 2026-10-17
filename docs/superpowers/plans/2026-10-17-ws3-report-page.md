# Workstream 3: The Report Page. Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The 6,461-line `template.py` becomes real HTML, CSS and JavaScript
files under `scanner/src/page/`. It happens in two phases:
- **Phase 1** only moves code. The page the scanner builds stays
  byte-identical.
- **Phase 2** restructures it:
  - each tab's code in one file;
  - one sortable table instead of five;
  - one flag helper instead of four;
  - shared small helpers;
  - dead code gone;
  - war losses with one owner.

  Every visible difference phase 2 makes is shown to the maintainer before
  workstream 4 starts.

**Architecture:**
- `scanner/build.rs` concatenates the files named, in order, in
  `scanner/src/page/order.txt` into `OUT_DIR/template.html`, as it now cuts
  that text out of `template.py`.
- `testkit/expected.py`'s `template()` reads the same list, so the page diff
  records keep meaning the same thing.
- All JavaScript stays inside the one async IIFE: the files are fragments of
  one script, not modules.

**Tech Stack:**
- Rust `build.rs` (no new dependencies).
- Plain HTML, CSS and JavaScript.
- The existing test kit: `suite.py`, `expected.py`, `boots.looked(probes=…)`
  and the `*_ui.py` checks, `looks.py` for screenshots, `baseline.py`.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-cleanup-design.md` (workstream 3, Decisions — "Visible differences in the page", Verification bar point 4).

## Global Constraints

- **Phase 1 must be byte-identical.** The `template.html` built from the new
  files is byte-identical to the one cut from `template.py` at `main`. Prove it
  with a SHA-256 of both.
- **Phase 2 rules.**
  - The page's payload stays identical. `baseline.py compare` holds, except
    that it is run with `--ignore payload.wars[].side_losses` from Task 5 on.
  - The page around the payload may change. Its records
    (`report.page.diff`) are re-recorded deliberately and the diff is read.
  - Each commit lists in its message any change a viewer could see.
- **Stop point.** At the end of phase 2, the maintainer sees before-and-after
  screenshots of every changed tab and approves or rejects each change.
  Workstream 4 does not start before that.
- **Checks after every commit.** Run `python testkit/all.py "$S" --mod "$M"
  --baseline ~/vic2-baseline`; every check must hold. After any change to a
  page file, rebuild the scanner first:
  `cargo build --release --manifest-path scanner/Cargo.toml`.
- **The mutation run.** When code a mutation patches moves, retarget the
  mutation and run it. At the end of each phase, run the full mutation run:
  all caught, apart from the Linux-only one.
- **No new dependencies.** No module bundler or build tool for the page:
  `build.rs` concatenates text.
- **Machine.**
  - Windows; one heavy command at a time, because this PC hard-resets under
    heavy load.
  - cargo is at `~/.cargo/bin`.
  - The pre-push hook is installed; nothing is pushed.
- **Branch and commits.**
  - Work on local branch `cleanup/report-page` from `main`.
  - Commit messages are plain sentences and end with
    `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A page file that ends without a newline, or a BOM, or CRLF from an
   editor.** Concatenation must reproduce the original bytes exactly. The
   SHA-256 check catches it, and `.gitattributes` keeps `scanner/src/page/**`
   at LF.
2. **A file added to `scanner/src/page/` but not named in `order.txt`, or
   named twice.** `build.rs` refuses to build and names the file. Test in
   Task 1.
3. **The template changed but the scanner was not rebuilt.** The build-id and
   staleness check (`staleness.py`) must see an edit to any page file. Test in
   Task 1.
4. **A refactor that changes behaviour only on a tab nobody clicks during the
   checks.** The tours in `boots.py` and the `*_ui.py` probes visit every tab
   and open every war. The pixel comparison in Task 7 covers each tab's first
   view.
5. **Screenshots that differ only because they are not deterministic.**
   Timing and fonts can change a picture between two runs of the same page.
   Two "before" shots are taken and compared, and a tab that differs between
   them is marked unreliable instead of reported as changed.

---

## Before Task 1

The follow-up branch `refs/heads/claude/frosty-panini-f59013` changes
`testkit/mutations.py` and `testkit/enginecheck.py`. Merging it into `main`
first is the maintainer's call. If they say yes, merge it, run the unit tests
and `all.py`, then start. If not, start without it, and expect a conflict in
`mutations.py` when it is merged later.

## Phase 1: move only

### Task 1: The page is real files, built in order

**Files:**
- Create: `scanner/src/page/order.txt`, listing one file per line, in page
  order.
- Create: `scanner/src/page/head.html`, `css/*.css`, `body.html`, `js/*.js`.
  The names follow the structural review's table:
  - `css/`: `base`, `map`, `tech`, `tables`, `wars`, `military`;
  - `js/`: `boot`, `core`, `widgets`, `shared`, `compare-trends`,
    `compare-head`, `military`, `stacked-bars`, `population-table`, `market`,
    `map`, `great-powers`, `tech`, `wars`, `wars-legacy`,
    `population-detail`, `tabs`, `export`.

  Cut at the existing section banners. Each file's content is exactly the
  original lines.
- Modify:
  - `scanner/build.rs`: read `order.txt`, concatenate, write
    `OUT_DIR/template.html`, and print `rerun-if-changed` for every page file.
    It refuses (panics, naming the file) when `src/page/` holds a page file
    `order.txt` does not name, or names one twice. The build-id walk already
    covers `src/`; drop the separate `template.py` source.
  - `testkit/expected.py`: `template()` returns the same concatenation, reading
    `order.txt`.
  - `testkit/staleness.py`: the build-id check copies `scanner/` alone. The
    page is under `src/`; drop `template.py`.
  - `testkit/mutate.py`: `rebuilds()` drops its `template.py` special case;
    `scanner/` covers the page.
  - `testkit/mutations.py`: the six rows that patch `template.py` patch the
    page file their text now lives in.
  - `.gitattributes`: `scanner/src/page/** text eol=lf`.
  - `DEVELOPING.md`, `scanner/README.md`, `README.md`: `template.py` becomes
    `scanner/src/page/` (`docrefs.py` holds this).
- Delete: `template.py`.

**Interfaces:**
- Produces `scanner/src/page/order.txt`, read by `build.rs` and
  `expected.template()`: page-relative paths, one per line, with blank lines
  and `#` comments ignored.

- [ ] **Step 1: Record the reference.** Take the SHA-256 of the page as
  `template.py` holds it now. That is the text between `TEMPLATE = r"""` and
  the next `"""`, the same slice `build.rs` takes.
- [ ] **Step 2: Write the failing check first.** In `testkit/staleness.py` (or
  a new `testkit/pagebuild.py` added to the suite), check that:
  - the page built by `build.rs` from `order.txt` has the reference SHA-256;
    this fails while there is no `order.txt`;
  - a page file missing from `order.txt` makes the build script exit non-zero,
    naming it (Review Focus 2);
  - an edit to any one page file changes `VIC2_BUILD_ID` (Review Focus 3).
- [ ] **Step 3: Split the page.** Use a throwaway script that cuts at the
  chosen line numbers, writes LF-only files, and asserts the concatenation
  equals the slice. Then update `build.rs`, `expected.py`, `staleness.py`,
  `mutate.py`, `mutations.py`, `.gitattributes` and the docs, and delete
  `template.py`.
- [ ] **Step 4: Verify.**
  - Rebuild the scanner.
  - The new check passes, with the reference SHA-256 matched.
  - `python testkit/mutate.py --dry` shows 0 NOAPPLY.
  - The six retargeted mutations are CAUGHT.
  - `all.py` with the baseline holds: page records unchanged, since the
    template text is identical.
  - `docrefs.py` passes.
- [ ] **Step 5: Commit.** "The report page is real HTML, CSS and JavaScript
  files under scanner/src/page/, built in the order order.txt gives, byte for
  byte the page template.py held".
- [ ] **Step 6: Run the full mutation run.** Expected: all caught but
  `keeper-folder-windows-only`.

## Phase 2: restructure

Before Task 2, take the "before" pictures and keep them outside the
repository. Use `testkit/looks.py`, once per tab and twice over (Review Focus
5), on a report built at the end of phase 1 from the baseline's nine NET saves
and the mod.

Each task below is one or more commits. After each commit:
- rebuild the scanner;
- run `all.py` with the baseline;
- read the re-recorded page diffs and say in the message what changed;
- retarget and run the mutations the change touches.

### Task 2: Dead code goes

- Remove:
  - the hidden culture table (`drawCultureTable`, `culSel`, `culState`,
    `culLimit`, its `<div hidden>`);
  - the hidden `#poptag` select. Population code calls the history chart
    directly.
  - unused CSS: `.ibbanner`, `.ibflags`, `.ibvs`, `.ibmore`,
    `.military-dossier*`, `.tablewrap.pinned`, `.groupcell`,
    `.return-details`. Check each with a grep of the page files first.
  - `isPlayer`;
  - `mapShowBattles`, which is always true;
  - the `belParties` and `Array.isArray` shims for data older than the
    present payload;
  - `DATA.x || {}` guards on keys `report.rs` always writes. Check each key in
    `report.rs` before removing its guard.
  - the navy `sections` callback and army `sections[2]` that nothing reads.
- Expected: no visible change. The page diff records change by the removed
  lines only.

### Task 3: Shared helpers replace their copies

- **Tables:**
  - one sortable table: `sortRows(rows, getter, state)` and
    `sortableHead(state, cols, redraw)`;
  - `renderTable`, `renderStrengthLedger`, `drawWarTable`, `warBattleTable`
    and `legacyBattles` use them.

  Keep each table's present default direction and blank placement as
  arguments, so sorting looks the same unless a difference is listed.
- **Flags:** one `flagSrc(tag)` with a DOM builder and an HTML builder,
  replacing `nationFlag`, `warFlag`, `ibFlag` and the override in
  `drawGreatPowers`.
- **Small helpers:**
  - `fillSelect`, `toggleButton`, `svgMessage` (using `var(--ink-dim)`);
  - `parseDate`/`dateYear` replacing `when`, `num` and the split logic;
  - `sumFact(tags, date, key)` replacing `groupStanding`, `groupCap`,
    `groupMob`, `groupMobilized` and `drawMilPies`'s `mobOf`.
- **Drawing:** one pie; one `downloadBlob`; one cached province-geometry pass
  in `map.js` used by Map, Population and Wars; the atlas uses `MAP_WATER`,
  `MAP_WILD` and `MAP_EDGE`.
- **Reorganise:** `powerKnown(tag, date)`, and the military dossier reading
  its rows directly, so `renderStrengthLedger` only renders.
- Expected visible differences:
  - the empty-chart message colour, if `#C9AC80` differs from `--ink-dim`;
  - possibly how blanks sort.

  List each one in the commit message.

### Task 4: Each tab's code in one file

- Regroup the JavaScript so each tab's code lives in one file named after the
  tab. The misleading banners go:
  - "NATIONS" is Compare's trends;
  - the Compare head-to-head sits under "MILITARY";
  - Population is in two places.

  Move `searchSelect` to `widgets.js`.
- Tabs register `{available, init, exportSubtitle}`, and the boot code loops
  over them, replacing the three separate places that hide tabs and
  `export.js`'s `switch` on `source.id`.
- Split `drawMilPies` (313 lines) and `mapRender` (241 lines) into data,
  summary text and drawing.
- Reformat the population detail code, written in minified style, to the
  rest of the file's style.
- Watch for `const` declarations used before their definition runs (the
  temporal dead zone) when code moves. The boot tour catches a throw.
- Expected: no visible change.

### Task 5: War losses have one owner

- The page computes each side's losses (`warSides`, `warSideLosses`). Drop
  `side_losses` from the payload in `scanner/src/engine/wars.rs`: the field,
  its computation, and its writing at the `"side_losses"` key. Delete
  `ibLosses` and inline what it did. The page comments citing `wars.py`'s
  `_side_losses` say what the rule is instead.
- This is the one payload change in scope.
  - Re-record `enginecheck`, `frontcheck`, `saveshapes` and `crossrows` with
    `--update-expected`.
  - Read the diff: only `side_losses` lines may go.
  - Compare against the baseline with `--ignore payload.wars[].side_losses`.
    Do not re-record the baseline.
- Retarget the war mutations that patched the losses code, and run them.

### Task 6: Phase 2 verification

- Run the full mutation run: all caught but the Linux-only one.
- Run `all.py` with the baseline (and its ignore). It holds.
- Run `docrefs.py`: no dead names. `DEVELOPING.md` and `scanner/README.md`
  list the page's files.

### Task 7: The maintainer sees every visible difference

- Take the "after" pictures exactly as the "before" ones: same report inputs,
  same tabs, twice.
- Write `scratchpad/page-compare.py`, a throwaway script. It decodes the PNGs
  with `expected.png_pixels`, and for each tab reports:
  - "same";
  - "unreliable" (the two befores differ);
  - "changed", with the bounding box of the changed pixels and how many
    pixels changed.
- For each changed tab, put the before and after side by side, with the
  changed box outlined, in one HTML page in the scratchpad. Show it to the
  maintainer in the browser pane, with the list of intended differences from
  the commit messages beside it.
- **Stop.** The maintainer approves or rejects each change. Revert each
  rejected change in its own commit, re-run `all.py`, and re-take only that
  tab's picture. Then hand over for integration.
