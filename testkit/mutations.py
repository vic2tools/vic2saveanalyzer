"""
The bugs `mutate.py` puts back, one row each.

A row names the bug, says in a sentence what it breaks, names the check
that should catch it, says what that check is handed, and lists the
patches that put it back: `(path, old, new)`, where `old` must appear
exactly once in the file, or `(path, old, new, count)` where it appears
`count` times (0 for "at least once").

`needs` is what the catcher is handed: "saves" (the save folder), "mod"
(the mod folder, after the saves), "one-save" (the first save in the
folder and a round count of one), "baseline" (the recorded baseline), or
plain arguments.

A fix that comes with a check comes with a row here, run once by hand with
its failure read: `mutate.py NAME ...`.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Mutation:
    name: str
    bug: str
    catcher: str
    needs: tuple
    patches: list


MUTATIONS = [
    Mutation(
        'window-shows-refusal-as-traceback',
        'the window does not catch a refused run, so the sentence the '
        'analyzer refused it with reaches the log as a traceback',
        'window.py', ('saves',),
        [
            ('gui.py', '        except RunError as refused:\n', '        except ZeroDivisionError as refused:\n'),
        ]),
    Mutation(
        'flag-gap-too-wide',
        'the flag gap that tells two games apart is ten times too wide, so '
        'a second game joins the first',
        'histories.py', (),
        [
            ('savehead.py', 'FLAG_GAP = 6\n', 'FLAG_GAP = 60\n'),
        ]),
    Mutation(
        'keeper-ignores-flag-gap',
        'the keeper files a save with the campaign whatever its flags say',
        'histories.py', (),
        [
            ('keeper.py', '        elif gap < FLAG_GAP:\n', '        elif True:\n'),
        ]),
    Mutation(
        'analyze-erases-share-settings',
        "remembering the window's paths writes them as the whole settings "
        'file, erasing the GitHub token and the report host',
        'window.py', ('saves',),
        [
            ('settings.py', '    held = load(path)\n', '    held = {}\n'),
        ]),
    Mutation(
        'refused-token-kept',
        'a token GitHub refuses stays held and is handed back on every '
        'press',
        'sharing.py', (),
        [
            ('app.py', '            settings.remember(github_token=None)\n', ''),
        ]),
    Mutation(
        'scanner-opens-console-window',
        'on Windows the window starts the scanner without CREATE_NO_WINDOW, '
        'so the windowed executable flashes a console window per run',
        'packing.py', (),
        [
            ('vic2_analyzer.py', '            status = _relayed(argv, fastscan._no_window(), hosted)', '            status = _relayed(argv, 0, hosted)'),
        ]),
    Mutation(
        'war-infobox-throws',
        'the infobox a war opens into throws, where no check had ever '
        'opened a war',
        'boots.py', ('--hostile',),
        [
            ('template.py', '  const opening = warOpening(w);\n', '  const opening = warOpening(w.unset.start);\n'),
        ]),
    Mutation(
        'war-casualties-by-nation',
        'the infobox lists what each nation lost, summed from the battles '
        "it led, which credits an ally's dead to whoever led the army",
        'war_legacy_ui.py', (),
        [
            ('template.py', '  const column = side => `<div class="ibtotal"><div class="ibwho">Total</div>`\n', '  const by = {1: new Map(), \'-1\': new Map()};\n  for (const b of w.battles) sides.battle(b).forEach((m, k) => {\n    const s = k ? b.d : b.a;\n    if (m) by[m].set(s[0], (by[m].get(s[0]) || 0) + s[2]);\n  });\n  const column = side => [...by[side]].map(([t, n]) => `<div class="ibnat">${ibFlag(t)}`\n      + `<div class="ibwho">${nameOf(t)}</div><span class="ibnum">${n}</span></div>`).join(\'\')\n    + `<div class="ibtotal"><div class="ibwho">Total</div>`\n'),
        ]),
    Mutation(
        'legacy-losses-by-country',
        "the legacy layout's country tables have the old window's Losses "
        "column back, each nation's losses summed from the battles it led",
        'war_legacy_ui.py', (),
        [
            ('template.py', '    + `<th class="num">Ended</th></tr></thead><tbody>`\n', '    + `<th class="num">Ended</th><th class="num">Losses</th></tr></thead><tbody>`\n'),
            ('template.py', '        + `<td class="num">${p.joined || \'—\'}</td><td class="num">${ended(p)}</td></tr>`)\n', '        + `<td class="num">${p.joined || \'—\'}</td><td class="num">${ended(p)}</td>`\n        + `<td class="num">${w.battles.reduce((n, b) => n + (b.a[0] === p.tag ? b.a[2] : 0)\n            + (b.d[0] === p.tag ? b.d[2] : 0), 0).toLocaleString()}</td></tr>`)\n'),
        ]),
    Mutation(
        'legacy-side-totals-swapped',
        "the legacy layout puts the defenders' losses in the attackers' "
        "panel and theirs in the defenders'",
        'war_legacy_ui.py', (),
        [
            ('template.py', "    + legacySide(w, 'attacker', lost, 1)\n", "    + legacySide(w, 'attacker', lost, -1)\n"),
            ('template.py', "    + legacySide(w, 'defender', lost, -1)\n", "    + legacySide(w, 'defender', lost, 1)\n"),
        ]),
    Mutation(
        'legacy-layout-forgotten',
        'the layout chosen for one war is not kept for the next one opened',
        'war_legacy_ui.py', (),
        [
            ('template.py', "document.getElementById('warback').onclick = () => {\n", "document.getElementById('warback').onclick = () => {\n  warView = 'infobox';\n"),
        ]),
    Mutation(
        'token-follows-redirect',
        'a redirect to another address is handed the GitHub token',
        'sharing.py', (),
        [
            ('publish.py', '        with _OPENER.open(request, timeout=TIMEOUT) as answer:', '        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:'),
        ]),
    Mutation(
        'publish-stall-raw',
        'GitHub stalling mid-answer raises a bare TimeoutError, not a '
        'sentence',
        'sharing.py', (),
        [
            ('publish.py', '    except (OSError, http.client.HTTPException) as err:\n        # Once connected', '    except ZeroDivisionError as err:\n        # Once connected'),
        ]),
    Mutation(
        'keeper-folder-windows-only',
        "the keeper's Open the folder calls os.startfile, which exists only "
        'on Windows',
        'window.py', ('saves',),
        [
            ('keeper_gui.py', '            keeper.open_with_system(where)\n        except OSError as err:', '            os.startfile(where)\n        except (OSError, AttributeError) as err:'),
        ]),
    Mutation(
        'stamp-leaves-out-min-pop',
        '--min-pop is declared as not changing the report, so a run that '
        'changes it is answered with the old one',
        'staleness.py', (),
        [
            ('run.py', '    min_pop: int = _setting(0, report=True)', '    min_pop: int = _setting(0, report=False)'),
        ]),
    Mutation(
        'relay-progress-lost',
        "the window's relay passes @progress on as text instead of moving "
        'the bar',
        'engine_runtime.py', (),
        [
            ('vic2_analyzer.py', '                    if word == "@progress":', '                    if word == "@progresss":'),
        ]),
    Mutation(
        'fixture-writes-through-link',
        'a test fixture truncates a real file through a symlink',
        'engine_runtime.py', (),
        [
            ('testkit/fixtures.py', '        if _linked(check):', '        if False:'),
        ]),
    Mutation(
        'stop-leaves-scanner-running',
        'Stop raises in the window but leaves the scanner reading',
        'engine_runtime.py', (),
        [
            ('vic2_analyzer.py', '        if proc.poll() is None:\n            proc.kill()\n', ''),
        ]),
    Mutation(
        'cross-min-pop',
        'the filter silently raises --min-pop to 1',
        'crossrows.py', (),
        [
            ('scanner/src/engine/finish.rs', '        wanted && nat.total_pop >= self.min_pop\n', '        wanted && nat.total_pop >= self.min_pop.max(1)\n'),
        ]),
    Mutation(
        'cross-player-nations-unread',
        '--player-nations goes unread',
        'crossrows.py', (),
        [
            ('scanner/src/engine/finish.rs', '    if let Some(t) = told {\n        return t.iter().cloned().collect();\n    }\n', ''),
        ]),
    Mutation(
        'cross-player-ignores-save',
        "the save's own player= marker goes unread",
        'crossrows.py', (),
        [
            ('scanner/src/engine/finish.rs', '    if !meta.player.is_empty() {', '    if false {'),
        ]),
    Mutation(
        'mod-overrides-explicit-default',
        'asking for the vanilla regiment size reads as asking for nothing',
        'crossrows.py', (),
        [
            ('scanner/src/front/mod.rs', '    let pop_per_regiment = match args.pop_per_regiment {', '    let pop_per_regiment = match args.pop_per_regiment.filter(|n| *n != POP_SIZE_PER_REGIMENT) {'),
        ]),
    Mutation(
        'cross-regiment-size',
        "the mod's POP_SIZE_PER_REGIMENT is ignored",
        'crossrows.py', (),
        [
            ('scanner/src/front/mod.rs', '            Some(v) if v.is_finite() && v.abs() < 9.0e18 => v.trunc() as i64,', '            Some(v) if v.is_finite() && v.abs() < 9.0e18 => POP_SIZE_PER_REGIMENT,'),
        ]),
    Mutation(
        'cross-mob-types',
        "the mod's pop list overrides --mob-types instead of deferring",
        'crossrows.py', (),
        [
            ('scanner/src/front/mod.rs', '    let mob_types: Vec<String> = match &args.mob_types {\n        Some(t) => t.clone(),\n        None => {', '    let mob_types: Vec<String> = match &args.mob_types {\n        _ => {'),
        ]),
    Mutation(
        'at-war-from-joins',
        "war = yes is answered from the history's joins, which keep a "
        'nation that made peace and miss one put into the war by hand',
        'mobrate.py', (),
        [
            ('scanner/src/engine/rules.rs', '        if !war.fighting.is_empty() {', '        if false {'),
        ]),
    Mutation(
        'explain-without-wars',
        'the save kept for the diagnostics loses its wars, so --explain-mob '
        'explains a rate without the war modifiers in it',
        'mobrate.py', (),
        [
            ('scanner/src/engine/explain.rs', '    let world = rules::save_world(meta, m);', '    let world = rules::save_world(&crate::engine::model::Meta { wars: Vec::new(), ..meta.clone() }, m);', 0),
        ]),
    Mutation(
        'cross-stamp-primary-only',
        'the --cross stamp covers only the largest campaign, so a new save '
        'in another is answered with the old report',
        'staleness.py', (),
        [
            ('scanner/src/front/cross.rs', '    let read: Vec<&Surveyed> = found.iter().filter(|e| e.mod_path.is_some()).collect();', '    let read: Vec<&Surveyed> = found.iter().max_by_key(|e| e.files.len()).into_iter().collect();'),
        ]),
    Mutation(
        'stamp-outlives-unfinished-run',
        'the stamp is not taken away before the files it describes are '
        'rewritten, so a run that dies -- or --no-html -- leaves it '
        'vouching for files it never saw',
        'staleness.py', (),
        [
            ('scanner/src/front/mod.rs', '        forget_stamp(&args.out);\n', ''),
        ]),
    Mutation(
        'locked-table-not-refused',
        'a table open in Excel is not refused in a sentence',
        'frontcheck.py', (),
        [
            ('scanner/src/engine/report.rs', '            Err(e) if held_elsewhere(&e) => refused.push(shown),', '            Err(e) if false && held_elsewhere(&e) => refused.push(shown),'),
        ]),
    Mutation(
        'stamp-ignores-a-setting',
        'the stamp leaves --min-pop out of the settings it hashes',
        'staleness.py', (),
        [
            ('scanner/src/front/mod.rs', '        ("min_pop", J::Int(args.min_pop)),\n', ''),
        ]),
    Mutation(
        'empty-table-left-stale',
        'a table with nothing in it this run is not written, so the last '
        "run's copy stays in the folder",
        'staleness.py', (),
        [
            ('scanner/src/engine/report.rs', '    for (k, name, cols) in order {\n', '    for (k, name, cols) in order {\n        if k > 0 && k < 100 && c.text[k].iter().all(|s| s.is_empty()) { continue; }\n'),
        ]),
    Mutation(
        'goal-judged-before-first-save',
        'a war that ended before the first save has its goal judged by that '
        "save against itself, and reads 'none taken'",
        'frontcheck.py', (),
        [
            ('scanner/src/engine/wars.rs', '        if !end.is_empty() && !ledger_dates.is_empty()\n            && ledger_dates[0] >= year_fraction(names::text(end)) {', '        if false {'),
        ]),
    Mutation(
        'same-date-read-twice',
        'two saves with the same in-game date are both read, doubling their '
        'rows in every table while the report shows one',
        'frontcheck.py', (),
        [
            ('scanner/src/front/mod.rs', '            *kept.last_mut().unwrap() = path;\n            continue;\n', '            kept.push(path);\n            keys.push(key);\n            continue;\n'),
        ]),
    Mutation(
        'run-never-pairs-a-game',
        'the run takes --mod-path and --game-root as given, unchecked',
        'frontcheck.py', (),
        [
            ('scanner/src/front/mod.rs', '        let (mod_path, game) = settle_game(args.mod_path.as_deref(), args.game_root.as_deref())?;', '        let (mod_path, game) = (args.mod_path.clone().or(args.game_root.clone()).unwrap_or_default(), args.game_root.clone().unwrap_or_default());'),
        ]),
    Mutation(
        'cut-save-read-as-whole',
        'a save that stops part-way through is read as if it were whole',
        'mangled.py', (),
        [
            ('scanner/src/engine/mod.rs', "    if end.map(|i| tail[i]) != Some(b'}') {", '    if false {'),
        ]),
    Mutation(
        'naval-base-int-becomes-float',
        'a nation with no naval base carries 0.0 where the table wrote 0',
        'saveshapes.py', (),
        [
            ('scanner/src/engine/model.rs', '    if n.naval_base_levels != 0.0 {', '    if true {'),
        ]),
    Mutation(
        'name-runs-as-script',
        "a war named <img onerror=...> runs its script when the report's "
        'Wars tab draws',
        'boots.py', ('--hostile',),
        [
            ('scanner/src/engine/finish.rs', "    if !s.contains(['<', '>']) {", '    if true {'),
        ]),
    Mutation(
        'chunk-stream-cut',
        "a save's state-history chunk loses the first byte of its gzip "
        "stream, so the page's chunk does not decompress",
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', 'deflate::gzip_level(raw.as_bytes(), &deflate::LEVEL5))', 'deflate::gzip_level(raw.as_bytes(), &deflate::LEVEL5)[1..])'),
        ]),
    Mutation(
        'level-five-stream-cut',
        "the level-5 compressor's stream loses its first byte, so it no "
        'longer decompresses',
        'enginecompress.py', ('scanner\\target\\release\\vic2scan.exe',),
        [
            ('scanner/src/deflate.rs', '"gz5" => gzip_level(&data, &LEVEL5),', '"gz5" => gzip_level(&data, &LEVEL5)[1..].to_vec(),'),
        ]),
    Mutation(
        'save-key-drops-reading',
        'a kept save is keyed without what it was read for, so a run asking '
        "for other pop types is served the last run's reading",
        'caching.py', (),
        [
            ('scanner/src/engine/cache.rs', '                     self.version, context))', '                     self.version, ""))'),
        ]),
    Mutation(
        'save-key-drops-time',
        'a kept save is keyed by its size alone, so a save rewritten to the '
        'same size is served from the old read',
        'caching.py', (),
        [
            ('scanner/src/engine/cache.rs', 'full.to_string_lossy(), meta.len(), mtime,', 'full.to_string_lossy(), meta.len(), 0,'),
        ]),
    Mutation(
        'raster-runs-merged-by-colour',
        'two colours naming one province, or a run carrying into the next '
        'row, ship as two runs where the map had one',
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', '            if Some(pid) == last {', '            if false {'),
        ]),
    Mutation(
        'raster-red-channel-dropped',
        'the bitmap is read without its red channel, so provinces told '
        'apart only by red come out as one',
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', 'row[at] as u32 | (row[at + 1] as u32) << 8 | (row[at + 2] as u32) << 16', 'row[at] as u32 | (row[at + 1] as u32) << 8'),
        ]),
    Mutation(
        'raster-samples-wrong-rows',
        'a scaled map samples every row instead of every scale-th',
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', 'offset + (oy * scale * stride) as u64', 'offset + (oy * stride) as u64'),
        ]),
    Mutation(
        'raster-text-miscounted',
        "the map's runs are spelled with every count one short",
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', '            b36(*c, &mut out);', '            b36(*c - 1, &mut out);'),
        ]),
    Mutation(
        'anchor-nearer-column-skipped',
        "a province's anchor measures only the column left of its middle",
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', 'vec![left, (left + 1).min(x1)]', 'vec![left]'),
        ]),
    Mutation(
        'anchor-sum-of-first-columns',
        'a stretch of a row counts only its first column toward the '
        "province's middle",
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', '        t[0] += ((x0 + x1) * n).div_euclid(2);', '        t[0] += x0 * n;'),
        ]),
    Mutation(
        'anchor-run-not-split-at-row-end',
        'a run carrying into the next row is measured as one stretch '
        'running off the edge of the map',
        'raster.py', (),
        [
            ('scanner/src/engine/mapflags.rs', 'let x1 = width.min(x0 + end - at) - 1;', 'let x1 = x0 + end - at - 1;'),
        ]),
    Mutation(
        'modread-ascii-words',
        "the pattern matcher's \\w takes ASCII only, where Python's takes "
        'the latin-1 letters too',
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/pyre.rs', '        | 0xb9 | 0xba | 0xbc..=0xbe | 0xc0..=0xd6 | 0xd8..=0xf6 | 0xf8..=0xff)', '        | 0xb9 | 0xba | 0xbc..=0xbe)'),
        ]),
    Mutation(
        'modread-lazy-is-greedy',
        'a lazy repeat is tried longest first',
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/pyre.rs', '                            for c in *min..=run {', '                            for c in (*min..=run).rev() {'),
        ]),
    Mutation(
        'modread-file-case-counted-twice',
        "the Rust reads a mod's Army_Tech.txt beside the game's "
        'army_tech.txt',
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/engine/modread.rs', '                chosen.set(lower(&name), (name, full));', '                chosen.set(name.clone(), (name, full));'),
        ]),
    Mutation(
        'modread-no-underscores',
        "the Rust's float() refuses 1_000, which Python reads as a thousand",
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/engine/modread.rs', '    let t = no_underscores(num_trim(s))?;', '    let t = num_trim(s).to_vec();'),
        ]),
    Mutation(
        'modread-block-name-empty',
        'a block where a flag type belongs reads as nothing, where Python '
        'keeps its repr',
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/engine/modread.rs', '                Some(v) => unquote(unquote(&str_of(v))).to_vec(),', '                Some(V::Str(v)) => unquote(v).to_vec(),\n                Some(_) => Vec::new(),'),
        ]),
    Mutation(
        'modread-ellipsis-is-space',
        "the localisation's 0x85 is stripped as a space, where Windows-1252 "
        'makes it an ellipsis',
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/engine/modread.rs', '    let sp = |c: u8| matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0xa0);', '    let sp = |c: u8| matches!(c, 0x09..=0x0d | 0x1c..=0x20 | 0x85 | 0xa0);'),
        ]),
    Mutation(
        'modread-last-name-wins',
        'a name defined twice in the localisation takes the later one',
        'modread.py', ('--rounds', '40'),
        [
            ('scanner/src/engine/modread.rs', '            if wanted.contains(&l.key) && !out.contains_key(&l.key) {', '            if wanted.contains(&l.key) {'),
        ]),
    Mutation(
        'modread-kept-copy-unsigned',
        "the engine keeps its read of a mod without the mod's signature in "
        'the key, so an edited mod is served from the old read',
        'modread.py', ('--rounds', '1'),
        [
            ('scanner/src/engine/cache.rs', '    let key = format!("mod|{}|{}|{}", path, signature, store.version);', '    let key = format!("mod|{}|{}|{}", path, signature.len() * 0, store.version);'),
        ]),
    Mutation(
        'front-stamp-ignores-settings',
        "the Rust's report stamp leaves the settings out, so a changed "
        '--min-pop is answered with the old report',
        'frontcheck.py', (),
        [
            ('scanner/src/front/mod.rs', '    digest.update(settings.as_bytes());\n', ''),
        ]),
    Mutation(
        'front-keeps-first-of-a-date',
        'two saves of one date keep the first-named rather than the later',
        'frontcheck.py', (),
        [
            ('scanner/src/front/mod.rs', '            *kept.last_mut().unwrap() = path;\n', ''),
        ]),
    Mutation(
        'front-no-expandvars',
        '$VAR in a path is taken literally',
        'frontcheck.py', (),
        [
            ('scanner/src/front/mod.rs', '    let saves_path = pypath::expanduser(&pypath::expandvars(&args.saves));', '    let saves_path = pypath::expanduser(&args.saves);'),
        ]),
    Mutation(
        'walk-navy-not-entered',
        'a save laid out another way loses the ships and embarked armies '
        'inside its navies',
        'frontcheck.py', (),
        [
            ('scanner/src/engine/walk.rs', '        } else if key == b"army" || key == b"navy" {', '        } else if key == b"army" {'),
        ]),
    Mutation(
        'walk-colonies-ignored',
        'a save laid out another way reads no state as colonial',
        'frontcheck.py', (),
        [
            ('scanner/src/engine/walk.rs', '                        let colonial = get(&block, b"is_colonial").is_some();', '                        let colonial = false;'),
        ]),
    Mutation(
        'cross-last-fit-wins',
        'of the mods that fit a campaign, the one it leaves most unused '
        'wins',
        'frontcheck.py', (),
        [
            ('scanner/src/front/cross.rs', '    fits.sort_by(|a, b| a.partial_cmp(b).unwrap());\n    let (_r, label, root) = fits.remove(0);', '    fits.sort_by(|a, b| a.partial_cmp(b).unwrap());\n    let (_r, label, root) = fits.pop().unwrap();'),
        ]),
    Mutation(
        'cross-flags-never-break',
        'a save from another game is never named, however many event flags '
        'it lacks',
        'frontcheck.py', (),
        [
            ('scanner/src/front/cross.rs', '        if worst >= 6 {', '        if worst >= 600 {'),
        ]),
    Mutation(
        'market-snapshot-goods-by-id',
        "the market snapshot's goods come out in the order the run met "
        'their names, not by name',
        'enginecheck.py', (),
        [
            ('scanner/src/names.rs', '/// Order by what the names say', 'pub fn id(s: Sym) -> u32 {\n    s.0\n}\n\n/// Order by what the names say'),
            ('scanner/src/engine/market.rs', '        goods.sort_by(|a, b| names::cmp(*a, *b));\n        let get', '        goods.sort_by_key(|g| names::id(*g));\n        let get'),
        ]),
    Mutation(
        'market-prices-goods-by-id',
        "a day's prices come out in the order the run met the goods' names, "
        'not by name',
        'enginecheck.py', (),
        [
            ('scanner/src/names.rs', '/// Order by what the names say', 'pub fn id(s: Sym) -> u32 {\n    s.0\n}\n\n/// Order by what the names say'),
            ('scanner/src/engine/market.rs', '        goods.sort_by(|a, b| names::cmp(*a, *b));\n        for good in goods {', '        goods.sort_by_key(|g| names::id(*g));\n        for good in goods {'),
        ]),
    Mutation(
        'war-side-units-reversed',
        "a battle's unit kinds are listed in the opposite order to the "
        "file's, which shows where two kinds have as many men",
        'enginecheck.py', (),
        [
            ('scanner/src/engine/wars.rs', '    let mut v: Vec<(&Sym, &i64)> = s.units.iter().collect();\n', '    let mut v: Vec<(&Sym, &i64)> = s.units.iter().collect();\n    v.reverse();\n'),
        ]),
    Mutation(
        'war-battles-reversed',
        "a war's battles are held in the opposite order to the file's, "
        'which shows where two battles share a date and a name',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/wars.rs', '        let mut battles: Vec<&Battle> = war.battles.values().collect();\n', '        let mut battles: Vec<&Battle> = war.battles.values().collect();\n        battles.reverse();\n'),
        ]),
    Mutation(
        'culture-ties-broken-by-name',
        'two cultures of the same size are listed alphabetically, not in '
        'the order the save first named them',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', '        cultures.sort_by(|a, b| b.1.cmp(a.1));\n', '        cultures.sort_by(|a, b| b.1.cmp(a.1).then(names::cmp(*a.0, *b.0)));\n'),
        ]),
    Mutation(
        'group-types-reversed',
        "a state's pop types are numbered in the opposite order to the one "
        "the save met them in, so the state chunk's words and layouts "
        'change',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/model.rs', 'Group { group: *group, size: st.total, literate: st.literate, types: pairs(&st.types),', 'Group { group: *group, size: st.total, literate: st.literate, types: { let mut v = pairs(&st.types); v.reverse(); v },'),
        ]),
    Mutation(
        'techs-ordered-by-name-number',
        "a nation's technologies are written in the order their names were "
        'first met in the run, not alphabetically, so technologies.csv and '
        "the page's lists change",
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', '        techs.sort_by(|a, b| names::cmp(*a, *b));\n', '        techs.sort_by_key(|t| t.index());\n'),
        ]),
    Mutation(
        'reform-mob-key-swapped',
        "a reform's mobilisation size is looked up with the option and the "
        'reform the wrong way round, so no reform grants any',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/rules.rs', '        let v = d.reform_mob(*reform, *option);\n', '        let v = d.reform_mob(*option, *reform);\n'),
        ]),
    Mutation(
        'national-value-ignored',
        "a nation's national value grants no mobilisation size",
        'enginecheck.py', (),
        [
            ('scanner/src/engine/rules.rs', '    let v = d.nv_mob(nat.nationalvalue);\n', '    let v = 0.0 * d.nv_mob(nat.nationalvalue);\n'),
        ]),
    Mutation(
        'modifier-impacts-ignored',
        "a nation's event modifiers add nothing to its mobilisation cap",
        'enginecheck.py', (),
        [
            ('scanner/src/engine/rules.rs', '        total += d.modifier_impact(*name);\n', '        total += 0.0 * d.modifier_impact(*name);\n'),
        ]),
    Mutation(
        'techs-without-branch',
        "every technology is filed under 'other' in technologies.csv and "
        'the page',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', 'dense.tech_group(*tech).unwrap_or(("other", "Other"))', 'dense.tech_group(*tech).filter(|_| false).unwrap_or(("other", "Other"))'),
        ]),
    Mutation(
        'cross-names-never-built',
        'a --cross run has no government names for its nations, so every '
        'label is the tag',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/mod.rs', '    let held_names: Vec<(String, String)> = if run.cross_part {', '    let held_names: Vec<(String, String)> = if false && run.cross_part {'),
        ]),
    Mutation(
        'row-facts-pop-types-dropped',
        'the pop_<type> columns of the main table read nought, as if the '
        'row had kept no pop types',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', '            pop_by_type: std::mem::take(&mut nat.pop_by_type),\n', '            pop_by_type: OMap::new(),\n'),
        ]),
    Mutation(
        'kept-units-left-behind',
        "a kept nation's units are not carried to the page, so no army is "
        'drawn',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', '        units_at: std::mem::take(&mut nat.units_at),\n', '        units_at: Vec::new(),\n'),
        ]),
    Mutation(
        'invention-trigger-inverted',
        'a trigger that asks whether a nation holds an invention is '
        'answered the other way',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/rules.rs', '.as_ref().map(|held| held.contains(text)));', '.as_ref().map(|held| !held.contains(text)));'),
        ]),
    Mutation(
        'army-kinds-tie-reversed',
        'two kinds with as many regiments in a province change places on '
        "the page's armies, as if the province's kinds were read last first",
        'enginecheck.py', (),
        [
            ('scanner/src/engine/report.rs', '                let mut ranked: Vec<&Stack> = types.iter().collect();', '                let mut ranked: Vec<&Stack> = types.iter().rev().collect();'),
        ]),
    Mutation(
        'army-provinces-reversed',
        "a nation's armies come out on the page with its provinces in the "
        'order last met first',
        'enginecheck.py', (),
        [
            ('scanner/src/country.rs', '        None => {\n            stacks.push(stack);\n            return;\n        }', '        None => {\n            stacks.insert(0, stack);\n            return;\n        }'),
        ]),
    Mutation(
        'ship-types-by-id',
        "ships_by_type.csv lists a nation's ships in the order the run met "
        'the names, not by name',
        'enginecheck.py', (),
        [
            ('scanner/src/names.rs', '/// Order by what the names say', 'pub fn id(s: Sym) -> u32 {\n    s.0\n}\n\n/// Order by what the names say'),
            ('scanner/src/engine/finish.rs', '        ship_types.sort_by(|a, b| names::cmp(a.kind, b.kind));', '        ship_types.sort_by_key(|s| names::id(s.kind));'),
        ]),
    Mutation(
        'regiment-types-by-id',
        "brigades_by_type.csv lists a nation's regiments in the order the "
        'run met the names, not by name',
        'enginecheck.py', (),
        [
            ('scanner/src/names.rs', '/// Order by what the names say', 'pub fn id(s: Sym) -> u32 {\n    s.0\n}\n\n/// Order by what the names say'),
            ('scanner/src/engine/finish.rs', '        regiments.sort_by(|a, b| names::cmp(a.0, b.0));', '        regiments.sort_by_key(|r| names::id(r.0));'),
        ]),
    Mutation(
        'ship-crew-dropped',
        "a ship's crew is not counted, so every fleet reads as crewed by "
        'its hull count',
        'enginecheck.py', (),
        [
            ('scanner/src/engine/finish.rs', '            let effective = Num::F(round(ship.crew, 3));', '            let effective = Num::I(ship.count);'),
        ]),
]
