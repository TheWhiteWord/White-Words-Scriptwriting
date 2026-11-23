#!/usr/bin/env node
// The Trash tab's render functions, executed for real.
//
//   node tests/trash_harness.js
//
// `web/js/views/trash.js` is a browser module, so a string check against its
// source proves nothing: this runs the repo's own file in a stub DOM and asserts
// the markup it produced. The payloads below are copies of what
// `app/routes/trash.py` returns (the field names are the contract; if the API
// changes, this file has to change with it, which is the point).
'use strict';

const fs = require('fs');
const path = require('path');

const WEB = path.join(__dirname, '..', 'src', 'story_architect', 'web');
const SRC = path.join(WEB, 'js', 'views', 'trash.js');

// ─── a DOM just big enough for init() to wire itself up ──────────────────────

const listeners = {};                    // element id -> [(event, fn)]
function stubEl(id) {
  const el = {
    id,
    innerHTML: '',
    textContent: '',
    hidden: false,
    disabled: false,
    title: '',
    value: '',
    dataset: {},
    classes: new Set(),
    classList: {
      add: (c) => el.classes.add(c),
      remove: (c) => el.classes.delete(c),
      contains: (c) => el.classes.has(c),
      toggle: (c, on) => (on ? el.classes.add(c) : el.classes.delete(c)),
    },
    addEventListener: (ev, fn) => { (listeners[id] = listeners[id] || []).push([ev, fn]); },
    querySelectorAll: () => [],
    querySelector: () => null,
  };
  return el;
}

const els = {};
const document = {
  getElementById: (id) => (els[id] = els[id] || stubEl(id)),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => stubEl('created'),
  body: { appendChild: () => {} },
};

global.document = document;
global.location = { hash: '#/p/save-the-children' };
global.window = global;
const DASH = {};
global.DASH = DASH;   // the module resolves DASH through window.DASH
let hooks = [];
DASH.escapeHtml = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
DASH.ENTITY_KIND_COLORS = { location: '#6bbfb0', world: '#e0a86b' };
DASH.onViewOpened = (fn) => hooks.push(fn);
DASH.initStory = () => {};
DASH.closePanel = () => {};
// panel-manager.js owns this predicate; a section body of `[placeholder …]` is a
// template marker, never prose, and every reader agrees on that one function.
DASH.isPlaceholderSection = (t) => /^\s*\[placeholder/i.test(String(t == null ? '' : t));
DASH.efDialog = () => ({ close() {}, busy() {}, error() {}, el: stubEl('dlg') });
DASH.efToast = () => {};

new Function('window', 'DASH', fs.readFileSync(SRC, 'utf8'))(global, global.DASH);

// ─── payloads: the API's own shapes ──────────────────────────────────────────

const SCENE = {
  type: 'scene', id: 'central-room-day', name: 'Central Room - Day',
  label: 'Scene', deleted_at: '2026-11-23T15:22:06+00:00',
  purge_eligible: false, preview: 'INT. THE CENTRAL ROOM - DAY', has_script: true,
  includes: [{ type: 'scene_beats', id: 'central-room-day-beats',
               name: 'central-room-day-beats', label: 'Scene Beats' }],
  restore: { blockers: [], warnings: {}, returned: { children: [], relations: 0, sections: 0 } },
};

const BEATS = {
  type: 'scene_beats', id: 'central-room-day-beats', name: 'central-room-day-beats',
  label: 'Scene Beats', deleted_at: '2026-11-20T21:40:00+00:00',
  purge_eligible: false, preview: 'central-room-day-beats', has_script: false, includes: [],
  restore: {
    blockers: [{
      code: 'parent_trashed',
      message: '“Central Room - Day” is still in the trash. Restore it too, or this comes back where nothing can see it.',
      fix: { entity_type: 'scene', id: 'central-room-day', name: 'Central Room - Day' },
    }],
    warnings: {},
    returned: { children: [], relations: 0, sections: 0 },
  },
};

const OLD_PLOT = {
  type: 'plot', id: 'the-resistance', name: 'The Resistance', label: 'Plot',
  deleted_at: '2026-09-21T08:00:00+00:00', purge_eligible: true,
  preview: 'Kael and Mira organise the children.', has_script: false, includes: [],
  restore: { blockers: [], warnings: {}, returned: { children: [], relations: 0, sections: 0 } },
};

const DETAIL = {
  entity: {
    id: 'central-room-day', type: 'scene', name: 'Central Room - Day', label: 'Scene',
    deleted_at: '2026-11-23T15:22:06+00:00', one_sentence: 'Kael finds the door unlocked.',
    has_script: true,
    fields: {
      name: 'Central Room - Day', one_sentence: 'Kael finds the door unlocked.',
      status: 'drafted', order_key: 1,
      parent: { id: 'the-discovery', entity_type: 'sequence', name: 'The Discovery' },
      location: { id: 'the-central-room', entity_type: 'location', name: 'The Central Room' },
    },
    extra: { int_ext: 'INT', time_of_day: 'DAY', cast: ['kael'] },
  },
  includes: [],
  sections: { Content: 'KAEL stands before the door.', Notes: 'The lock was never engaged.' },
  relations: {
    out: [], in: [],
    all: [{ id: 'kael', entity_type: 'character', name: 'Kael', kind: 'character_scene',
            note: '', live: false }],
  },
  referenced_by: [],
  restore: {
    blockers: [],
    warnings: {
      reference_in_trash: [
        { entity_type: 'location', id: 'the-central-room', name: 'The Central Room', field: 'location' },
        { entity_type: 'character', id: 'kael', name: 'Kael', field: 'character_scene' },
      ],
      reference_purged: [
        { entity_type: 'plot', id: 'a-gone-plot', name: 'a-gone-plot', field: 'plot_climax' },
      ],
      stranded_children: [
        { entity_type: 'scene_beats', id: 'beats-old', name: 'beats-old', field: 'parent' },
      ],
    },
    returned: { children: [], relations: 1, sections: 2, referenced_by: [] },
  },
  purge: { items: [], affected: [], backup: true },
};

const PREVIEW = {
  items: [
    { id: 'kael', type: 'character', name: 'Kael', label: 'Character' },
    { id: 'central-room-day', type: 'scene', name: 'Central Room - Day', label: 'Scene' },
    { id: 'central-room-day-beats', type: 'scene_beats', name: 'central-room-day-beats', label: 'Scene Beats' },
  ],
  affected: [
    { entity_type: 'scene', id: 'central-room-night', name: 'Central Room - Night', field: '' },
    { entity_type: 'scene', id: 'central-room-night', name: 'Central Room - Night', field: 'location' },
  ],
  backup: true,
  refusal: null,
};

// ─── the checks ──────────────────────────────────────────────────────────────

let fails = 0;
function check(name, fn) {
  try { fn(); console.log('  ok   ' + name); }
  catch (e) { fails++; console.log('  FAIL ' + name + ' -> ' + e.message); }
}
function eq(actual, expected, what) {
  const a = JSON.stringify(actual), b = JSON.stringify(expected);
  if (a !== b) throw new Error((what || 'value') + ': expected ' + b + ', got ' + a);
}
function has(haystack, needle, what) {
  if (!String(haystack).includes(needle)) {
    throw new Error((what || 'markup') + ' is missing ' + JSON.stringify(needle));
  }
}
function hasNot(haystack, needle, what) {
  if (String(haystack).includes(needle)) {
    throw new Error((what || 'markup') + ' must not contain ' + JSON.stringify(needle));
  }
}

const D = DASH;

const NOW = new Date('2026-11-23T15:30:00Z');

console.log('trash view');

check('grouping is by calendar day, not elapsed hours', () => {
  eq(D.trashBucket('2026-11-23T09:00:00Z', NOW), 'Deleted today');
  eq(D.trashBucket('2026-11-23T00:01:00Z', NOW), 'Deleted today');
  eq(D.trashBucket('2026-11-22T23:59:00Z', NOW), 'Deleted yesterday');
  eq(D.trashBucket('2026-11-20T12:00:00Z', NOW), 'Earlier this week');
  eq(D.trashBucket('2026-11-05T12:00:00Z', NOW), 'This month');
  eq(D.trashBucket('2026-09-01T12:00:00Z', NOW), 'Older');
  // A stamp the backend refuses to write must not become "NaN days".
  eq(D.trashBucket('not-a-date', NOW), 'Older');
});

check('a bundle row nests its children and counts them', () => {
  const html = D.trashRowHtml(SCENE, new Set());
  has(html, 'data-row="scene:central-room-day"');
  has(html, 'data-check="scene:central-room-day"');
  has(html, 'Central Room - Day');
  has(html, 'INT. THE CENTRAL ROOM - DAY');
  has(html, 'class="trash-include"');
  has(html, 'Scene Beats', 'the child is labelled in words');
  has(html, '2 entities');
});

check('a blocked row says so, and a +30-day row wears its chip', () => {
  has(D.trashRowHtml(BEATS, new Set()), 'restore blocked');
  has(D.trashRowHtml(OLD_PLOT, new Set()), '30+ days');
  hasNot(D.trashRowHtml(SCENE, new Set()), 'restore blocked');
  hasNot(D.trashRowHtml(SCENE, new Set()), '30+ days');
});

check('a selected row is marked, an unselected one is not', () => {
  has(D.trashRowHtml(SCENE, new Set(['scene:central-room-day'])), 'trash-row selected');
  has(D.trashRowHtml(SCENE, new Set()), 'trash-row"');
  hasNot(D.trashRowHtml(SCENE, new Set()), 'trash-row selected');
});

check('ids go through data-* and no inline handler is built from one', () => {
  const html = D.trashRowHtml(SCENE, new Set()) + D.trashPanelBody(DETAIL) + D.trashPurgeBody(PREVIEW);
  hasNot(html, 'onclick', 'row/panel/purge markup');
  hasNot(html, '<script', 'row/panel/purge markup');
});

check('a name with markup in it is text, not markup', () => {
  const evil = Object.assign({}, SCENE, {
    name: '<img src=x onerror="alert(1)">',
    includes: [{ type: 'scene_beats', id: 'x"><b>', name: '<b>bold</b>', label: 'Scene Beats' }],
  });
  const html = D.trashRowHtml(evil, new Set());
  hasNot(html, '<img');
  hasNot(html, '<b>');
  has(html, '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
});

check('groups keep the time order and drop the empty buckets', () => {
  const html = D.trashGroupHtml([OLD_PLOT, SCENE, BEATS], new Set(), NOW);
  const titles = [...html.matchAll(/trash-group-title">([^<]+)</g)].map((m) => m[1]);
  eq(titles, ['Deleted today', 'Earlier this week', 'Older']);
});

check('the filter reads name, type and preview, and ignores case', () => {
  eq(D.trashFilterRows([SCENE, BEATS, OLD_PLOT], '').length, 3);
  eq(D.trashFilterRows([SCENE, BEATS, OLD_PLOT], 'KAEL').map((i) => i.id), ['the-resistance']);
  eq(D.trashFilterRows([SCENE, BEATS, OLD_PLOT], 'nothing-here').length, 0);
  eq(D.trashFilterRows([SCENE, BEATS, OLD_PLOT], 'CENTRAL').map((i) => i.id),
     ['central-room-day', 'central-room-day-beats']);
  eq(D.trashFilterRows([SCENE, BEATS, OLD_PLOT], 'scene_beats').length, 1);
});

check('a selection is pruned to what still exists', () => {
  const sel = new Set(['scene:central-room-day', 'character:kael']);
  D.trashPruneSelection(sel, [SCENE]);
  eq([...sel], ['scene:central-room-day']);
});

check('the panel names what a link points at', () => {
  const html = D.trashPanelBody(DETAIL);
  has(html, 'The Central Room');
  has(html, 'Kael');
  has(html, 'cast', 'the relation kind in a word');
});

check('every list that can come back is tick boxes — except the one that cannot', () => {
  const html = D.trashPanelBody(DETAIL);
  has(html, 'data-extra="location:the-central-room"');
  has(html, 'data-extra="character:kael"');
  has(html, 'data-extra="scene_beats:beats-old"');
  has(html, 'Children that stay hidden');
  has(html, 'Links that stay hidden');
  // A purged link is plain text: a box there could not do anything.
  has(html, 'trash-warn-line plain');
  hasNot(html, 'data-extra="plot:a-gone-plot"');
  hasNot(html, 'Restore these too');   // no per-line button: the footer acts
});

check('a blocker renders its reason and a box that fixes it', () => {
  const html = D.trashPanelBody(Object.assign({}, DETAIL, {
    restore: { blockers: BEATS.restore.blockers, warnings: {}, returned: {} },
  }));
  has(html, 'still in the trash');
  has(html, 'data-extra="scene:central-room-day"');
  hasNot(html, 'Restore these too');
});

check('prose puts Content first and skips the template placeholder', () => {
  const html = D.trashPanelBody(Object.assign({}, DETAIL, {
    sections: { Background: 'Born inside The I.', Content: 'KAEL stands.',
                Extra: '[placeholder — Scene/Content]' },
  }));
  const order = ['Content', 'Background'].map((k) => html.indexOf('>' + k + '<'));
  if (order[0] < 0 || order[1] < 0) throw new Error('a section heading is missing');
  if (order[0] > order[1]) throw new Error('Content is not first');
  hasNot(html, '[placeholder');
});

check('the footer names the blocker and stays inert until it is ticked', () => {
  const T = D.trashState;
  T.detail = Object.assign({}, DETAIL, {
    restore: { blockers: BEATS.restore.blockers, warnings: {}, returned: {} },
  });
  T.pending.clear();

  let html = D.trashPanelFooter();
  has(html, 'Restore “Central Room - Day” first — tick it above');
  has(html, 'class="btn btn-primary" data-panel="restore" disabled', 'the inert primary');

  T.pending.add('scene:central-room-day');
  html = D.trashPanelFooter();
  hasNot(html, 'disabled');
  has(html, 'Restore 2');
  has(html, '2 items come back together');

  T.pending.clear();
});

check('the footer counts the batch and says what the press will do', () => {
  const T = D.trashState;
  T.detail = DETAIL;
  T.pending.clear();
  has(D.trashPanelFooter(), 'Deleting permanently cannot be undone.');
  has(D.trashPanelFooter(), 'Restore</button>');
  T.pending.add('character:kael');
  has(D.trashPanelFooter(), 'Restore 2');
  has(D.trashPanelFooter(), 'and the one you ticked');
  T.pending.clear();
});

check('the preview opens narrow and widens only when the reader asks', () => {
  const T = D.trashState;
  T.detail = DETAIL;
  T.pending.clear();
  T.wide = false;
  let html = D.trashPanelFooter();
  has(html, 'data-panel="widen"', 'the width toggle');
  has(html, 'aria-pressed="false"');
  has(html, 'title="Widen the preview"');

  T.wide = true;                       // what the toggle writes, and what the
  html = D.trashPanelFooter();         // next row's preview then reopens at
  has(html, 'aria-pressed="true"');
  has(html, 'title="Narrow the preview"');
  T.wide = false;
});

check('the purge card names every item, every consequence, and the backup', () => {
  const html = D.trashPurgeBody(PREVIEW);
  ['Kael', 'Central Room - Day', 'central-room-day-beats'].forEach((n) => has(html, n));
  has(html, 'Also affected');
  has(html, 'Central Room - Night');
  has(html, 'loses its location');
  has(html, 'loses a reference');
  has(html, 'before-purge');
  has(html, 'next export', 'never claim the Markdown is already gone');
});

check('the tab is wired to opening its view, and asks for the badge at boot', () => {
  if (hooks.length !== 1) throw new Error('expected one onViewOpened hook, got ' + hooks.length);
  // The hook only paints the badge for the trash view; every other view drops
  // the wide panel the preview set.
  els['detail-panel'] = els['detail-panel'] || stubEl('detail-panel');
  els['detail-panel'].classes.add('panel-wide');
  hooks[0]('scenes');
  if (els['detail-panel'].classes.has('panel-wide')) {
    throw new Error('leaving the trash view must release the wide panel');
  }
});

console.log(fails ? `\n${fails} check(s) failed` : '\nall checks passed');
process.exit(fails ? 1 : 0);
