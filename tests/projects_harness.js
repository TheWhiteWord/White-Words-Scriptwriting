#!/usr/bin/env node
// The projects page's render functions and the branch graph's layout, executed for real.
//
//   node tests/projects_harness.js
//
// `web/js/projects.js` and `web/js/history-graph.js` are browser modules. This runs the
// repo's own files with no DOM (the controller only wires itself up when there is one)
// and asserts the markup and geometry they produce. The payloads are the shapes
// `GET /api/projects` and `GET /api/projects/<slug>/history/` return; if the API
// changes, this file has to change with it, which is the point.
'use strict';

const path = require('path');

global.window = global;
const JS = path.join(__dirname, '..', 'src', 'white_words', 'scriptwriting', 'web', 'js');
require(path.join(JS, 'history-graph.js'));
require(path.join(JS, 'projects.js'));
require(path.join(JS, 'draft-chip.js'));

const R = global.DASH.projectsRender;
const G = global.DASH.historyGraph;
let ran = 0;
const failures = [];

function check(name, cond, detail) {
  ran += 1;
  if (cond) console.log('ok   ' + name);
  else { failures.push(name); console.log('FAIL ' + name + (detail ? '\n     ' + detail : '')); }
}

const NOW = Date.parse('2026-11-26T12:00:00Z');
const snap = (id, branch, label, parents, extra) => Object.assign({ id, branch_id: branch, seq: 1, label, note: '', created_at: '2026-11-26T11:00:00+00:00', parents }, extra || {});
const branch = (id, base, extra) => Object.assign({ id, name: id, base_snapshot_id: base, is_current: false, created_at: '2026-11-26T10:00:00+00:00', pending_merge_parents: [] }, extra || {});

// main: d1 → d2; alt branched from d1 with d3; alt is current and has 2 open changes.
const history = () => ({
  branches: [branch('alt', 'd3', { is_current: true, created_at: '2026-11-26T10:00:00+00:00' }), branch('main', 'd2')],
  snapshots: [snap('d1', 'main', 'Draft 1', []), snap('d2', 'main', 'Draft 2', ['d1']), snap('d3', 'alt', 'Garden <opening>', ['d1'], { note: 'alt take' })],
  current: 'alt',
  head: { alt: { changed: true, changes: 2 }, main: { changed: false, changes: 0 } },
  picked_from: [],
});

// ─── time ───
check('a minute-old save reads in minutes', R.ago('2026-11-26T11:58:00Z', NOW) === '2 mins ago');
check('a fresh save reads just now', R.ago('2026-11-26T11:59:40Z', NOW) === 'just now');
check('an hour-old save reads in hours', R.ago('2026-11-26T11:00:00Z', NOW) === '1 hour ago');
check('an unparseable time reads as nothing', R.ago('not a date', NOW) === '');

// ─── the card ───
const listed = (extra) => Object.assign({ slug: 'save-the-children', name: 'Save the Children', has_db: true, current_branch: 'alt', current_draft: 'Garden opening', branch_count: 2, last_saved: '2026-11-26T11:00:00Z', changes_since_save: 3 }, extra || {});
let html = R.cardHtml(listed(), { open: false }, NOW);
check('a collapsed card has no body', !/class="pj-body"/.test(html));
check('the card names branch, draft and branch count', /alt · Garden opening · 2 branches · saved 1 hour ago/.test(html));
check('unsaved changes show as a count since the draft', /3 changes since Garden opening/.test(html));
check('a clean project says up to date', /up to date/.test(R.cardHtml(listed({ changes_since_save: 0 }), { open: false }, NOW)));
check('one change is singular', /1 change since/.test(R.cardHtml(listed({ changes_since_save: 1 }), { open: false }, NOW)));
check('a project with no history says so and shows no chip', /No drafts saved yet/.test(R.cardHtml(listed({ branch_count: 0, current_draft: null, current_branch: null, changes_since_save: 0 }), { open: false }, NOW)) && !/pj-chip/.test(R.cardHtml(listed({ branch_count: 0 }), { open: false }, NOW)));
check('a project with no database cannot be opened', /data-act="open"[^>]* disabled/.test(R.cardHtml(listed({ has_db: false }), { open: false }, NOW)));
check('the toggle reports its state to assistive tech', /aria-expanded="false"/.test(html) && /aria-expanded="true"/.test(R.cardHtml(listed(), { open: true, hist: { state: 'loading' } }, NOW)));
check('an opening card says it is loading', /Loading history/.test(R.cardHtml(listed(), { open: true, hist: { state: 'loading' } }, NOW)));
check('a failed history load shows the server sentence', /boom &lt;b&gt;/.test(R.cardHtml(listed(), { open: true, hist: { state: 'error', message: 'boom <b>' } }, NOW)));

// ─── escaping and handlers ───
const hostile = history();
hostile.snapshots[2].label = '"><img src=x onerror=alert(1)>';
hostile.branches[1].name = '</div><script>alert(2)</script>';
const hostileHtml = R.cardHtml(listed({ name: '<b>x</b>' }), { open: true, hist: { state: 'ready', data: hostile } }, NOW);
check('no label or name can open a tag', !/<img src=x|<script>|<b>x/.test(hostileHtml));
check('no inline handler is built anywhere', !/\bon[a-z]+\s*=\s*["']/.test(hostileHtml.replace(/data-[a-z]+="[^"]*"/g, '')));

// ─── the open card ───
const open = (h, extra) => R.cardHtml(listed(extra), { open: true, hist: { state: 'ready', data: h } }, NOW);
html = open(history());
check('Save draft is enabled when the open draft changed', /data-act="save"(?![^>]*disabled)/.test(html));
const clean = history();
clean.head.alt = { changed: false, changes: 0 };
check('Save draft is disabled when nothing changed', /data-act="save"[^>]* disabled/.test(open(clean)));
check('the current branch offers Open, the other Switch and open', /data-act="open"[^>]*>Open</.test(html) && (html.match(/data-act="switch"/g) || []).length === 1);
check('the current branch cannot be deleted', /data-act="delete-branch"[^>]*data-id="alt"[^>]* disabled/.test(html) && /data-act="delete-branch"[^>]*data-id="main"(?![^>]* disabled)/.test(html));
check('a draft a branch starts from cannot be deleted', /data-act="delete-draft"[^>]*data-id="d3"[^>]* disabled/.test(html) && /data-act="delete-draft"[^>]*data-id="d2"[^>]* disabled/.test(html));
check('a draft nothing starts from can be deleted', /data-act="delete-draft"[^>]*data-id="d1"(?![^>]* disabled)/.test(html));
check('drafts are listed newest first', html.indexOf('data-row="snapshot:d3"') < html.indexOf('data-row="snapshot:d1"'));
check('a branch row says what its open draft holds', /Open draft: 2 changes since Garden &lt;opening&gt;/.test(html) && /Open draft: no changes since Draft 2/.test(html));
check('a project with no history offers a first save', /Save first draft/.test(open({ branches: [], snapshots: [], current: null, head: {}, picked_from: [] })));

// ─── graph geometry ───
const g = G.layout(history());
const node = (kind, id) => g.nodes.find((n) => n.kind === kind && n.id === id);
check('the branch holding the first draft is the top lane even on a tie', node('draft', 'd1').y < node('draft', 'd3').y);
check('a child sits one column right of its parent', node('draft', 'd2').x === node('draft', 'd1').x + G.DX && node('draft', 'd3').x === node('draft', 'd1').x + G.DX);
check('a branch tip sits one column right of its draft', node('tip', 'main').x === node('draft', 'd2').x + G.DX && node('tip', 'alt').x === node('draft', 'd3').x + G.DX);
check('the tip carries its change count', node('tip', 'alt').changes === 2 && node('tip', 'alt').changed && !node('tip', 'main').changed);
check('edges are parents plus one tip edge per branch', g.edges.filter((e) => e.kind === 'parent').length === 2 && g.edges.filter((e) => e.kind === 'tip').length === 2);
check('the canvas holds every node', g.nodes.every((n) => n.x < g.width && n.y < g.height));

const merged = history();
merged.snapshots.push(snap('d4', 'main', 'Merged', ['d2', 'd3']));
merged.branches[1].base_snapshot_id = 'd4';
const gm = G.layout(merged);
check('a second parent is a merge edge', gm.edges.filter((e) => e.kind === 'merge').length === 1);
check('a merge sits right of both parents', gm.nodes.find((n) => n.id === 'd4').x > gm.nodes.find((n) => n.id === 'd3').x);

const pending = history();
pending.branches[1].pending_merge_parents = ['d3'];
pending.picked_from = [{ branch: 'main', source: { kind: 'snapshot', id: 'd1' } }, { branch: 'main', source: { kind: 'snapshot', id: 'd1' } }, { branch: 'main', source: { kind: 'snapshot', id: 'gone' } }];
const gp = G.layout(pending);
check('a pending merge parent is a dashed edge to the tip', gp.edges.filter((e) => e.kind === 'pending').length === 1);
const complete = history();
complete.branches[1].pending_merge_parents = ['d3'];
complete.picked_from = [{ branch: 'main', source: { kind: 'snapshot', id: 'd3' } }];
check('a pick already drawn as a pending merge is not drawn twice', G.layout(complete).edges.filter((e) => e.kind === 'pick').length === 0);
check('a pick is one edge however often it was applied, and one from a missing draft is dropped', gp.edges.filter((e) => e.kind === 'pick').length === 1);

const orphan = history();
orphan.snapshots[0].branch_id = 'deleted-branch';
check('a draft on a deleted branch lands on a lane that reaches it', Number.isFinite(G.layout(orphan).nodes.find((n) => n.id === 'd1').y));
check('an empty history lays out without throwing', G.layout({ branches: [], snapshots: [] }).nodes.length === 0);

const svg = G.svg(history());
check('branch names are in their own column, outside the scrolling canvas', /<svg class="hg-lanes"[^>]*aria-hidden="true">[\s\S]*<div class="hg-scroll"><svg class="hg"/.test(svg) && !/<div class="hg-scroll">[\s\S]*hg-lane /.test(svg));
check('a lane label carries the full branch name', /<title>alt<\/title>alt/.test(svg));
check('the svg names its size for assistive tech', /role="img" aria-label="Branch graph: 2 branches, 3 drafts"/.test(svg));
check('graph nodes carry their ids as data, never as handlers', /data-snapshot="d1"/.test(svg) && /data-branch="alt"/.test(svg) && !/onclick/.test(svg));
check('the svg escapes a draft label', !/<opening>/.test(svg) && /Garden &lt;opening&gt;/.test(svg));
check('a long label is clipped', /…/.test(G.svg(Object.assign(history(), { snapshots: [snap('d1', 'main', 'A very long draft name indeed', [])] }))));

// ─── the draft chip ───
const C = global.DASH.draftChip;
const status = (extra) => Object.assign({ branch_count: 2, current_branch: 'alt', current_draft: 'Garden opening', changes_since_save: 0, next_draft_number: 2 }, extra || {});
check('an unknown status draws nothing', C.render(null) === '');
check('a project with no history offers a first save', /No drafts yet/.test(C.render(status({ branch_count: 0 }))) && /Save first draft/.test(C.render(status({ branch_count: 0 }))));
check('the chip names branch and draft', /alt · Garden opening/.test(C.render(status())));
check('a clean project has Save draft disabled and says why', /data-dc="save" disabled title="Nothing has changed since Garden opening\."/.test(C.render(status())) && !/dc-chip changed/.test(C.render(status())));
check('unsaved changes mark the chip and enable Save draft', /dc-chip changed/.test(C.render(status({ changes_since_save: 3 }))) && /3 changes/.test(C.render(status({ changes_since_save: 3 }))) && /data-dc="save">Save draft/.test(C.render(status({ changes_since_save: 3 }))));
check('one change is singular', /· 1 change"/.test(C.render(status({ changes_since_save: 1 }))));
check('the chip links to the projects page by data attribute, not a handler', /data-dc="projects"/.test(C.render(status())) && !/\bon[a-z]+\s*=/.test(C.render(status())));
check('a hostile branch or draft name cannot open a tag', !/<img|<script/.test(C.render(status({ current_branch: '<img src=x>', current_draft: '"><script>' }))));

console.log(failures.length ? '\n' + failures.length + ' FAILED' : '\nall checks passed (' + ran + ' checks)');
process.exit(failures.length ? 1 : 0);
