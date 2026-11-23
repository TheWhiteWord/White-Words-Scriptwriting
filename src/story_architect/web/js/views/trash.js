/* ─── Trash ───────────────────────────────────────────────────────────────────
   The tab that manages what a delete only hid.

   A delete in this app is a flag (`is_deleted`, `deleted_at`) — nothing is
   moved, so a restore clears the flag and gives back exactly what was there.
   The rules live in `core/trash.py`, shared with the agent's `story_admin` tool,
   and the API in `app/routes/trash.py`. This file only draws them, and it does
   not invent a second copy of any rule:

     * one row per DELETION — the root plus the children flagged by that same
       operation, nested and read-only (the backend's bundle);
     * restore is reversible, so it never asks; deleting permanently always asks,
       names every item, and says a backup is taken;
     * a blocked restore is shown before it can be clicked (the row says so, the
       button is inert), and the panel's tick boxes are the only way to widen a
       restore batch.

   Ids never appear in an inline handler: rows carry `data-row` / `data-check`
   and two listeners on the list do the work, so a name with a quote in it is a
   name, not markup.
   ───────────────────────────────────────────────────────────────────────────── */
window.DASH = window.DASH || {};
(function (D) {
  'use strict';

  const h = (s) => D.escapeHtml(String(s == null ? '' : s));
  const slugFromHash = () => {
    const m = (location.hash || '').match(/^#\/p\/([^/?]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  };
  const toast = (m, k) => { if (D.efToast) D.efToast(m, k); };
  const keyOf = (type, id) => type + ':' + id;
  const splitKey = (k) => { const i = k.indexOf(':'); return [k.slice(0, i), k.slice(i + 1)]; };
  const plural = (n, one, many) => (n === 1 ? '1 ' + one : n + ' ' + (many || one + 's'));

  // A relation kind in the words a person uses, so a link reads the same here
  // and in the purge card. Mirrors `KIND_WORDS` in the panel tabs.
  const KIND_WORDS = {
    character_scene: 'cast',
    plot_setup: 'plot role', plot_inciting_incident: 'plot role',
    plot_complication: 'plot role', plot_crisis: 'plot role',
    plot_climax: 'plot role', plot_resolution: 'plot role',
    location_scene: 'location',
    location_variant: 'variant of', world_variant: 'variant of',
    value_scene: 'value turn', value_turn: 'value turn',
  };
  const kindWord = (field) => KIND_WORDS[field] || String(field || '').replace(/_/g, ' ');

  // The pip colours the entity views already use (colors.js), so a row in the
  // trash is the same colour as the same thing in its tab.
  const TYPE_COLOR = {
    character: 'var(--role-protagonist)',
    scene: 'var(--role-supporting)',
    location: D.ENTITY_KIND_COLORS ? D.ENTITY_KIND_COLORS.location : '#6bbfb0',
    world: D.ENTITY_KIND_COLORS ? D.ENTITY_KIND_COLORS.world : '#e0a86b',
    plot: 'var(--role-antagonist)',
    relationship: 'var(--role-entity)',
    value: 'var(--role-supporting)',
    scene_beats: 'var(--muted-foreground)',
  };
  const typeColor = (type) => TYPE_COLOR[type] || 'var(--muted-foreground)';

  const T = {
    items: [], countsByType: {}, entities: 0, purgeDays: 30,
    selected: new Set(),      // `type:id` of the rows ticked in the list
    pending: new Set(),       // `type:id` of the panel's "bring it back as well"
    filter: '',
    open: null,               // `type:id` of the row whose panel is open
    detail: null,
    wide: false,              // the reader widened the preview; forgotten on leaving the tab
    loadedAt: 0,
  };

  // ─── talking to the server ─────────────────────────────────────────────────

  async function api(path, opts) {
    const slug = slugFromHash();
    if (!slug) throw new Error('No project open');
    const o = Object.assign({
      headers: { 'Content-Type': 'application/json', 'X-Story-Architect': '1' },
    }, opts || {});
    const res = await fetch('/api/projects/' + encodeURIComponent(slug) + path, o);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = (body && body.error) || {};
      const e = new Error(err.message || res.statusText || 'Request failed');
      e.status = res.status;
      e.body = err;
      throw e;
    }
    return body;
  }

  const post = (path, payload) => api(path, { method: 'POST', body: JSON.stringify(payload || {}) });

  // ─── time, in words a person uses ──────────────────────────────────────────

  function relative(stamp, now) {
    const then = new Date(stamp);
    if (isNaN(then)) return '—';                  // a stamp the backend refuses to write
    const mins = Math.max(0, Math.round(((now || new Date()) - then) / 60000));
    if (mins < 2) return 'just now';
    if (mins < 60) return mins + ' minutes ago';
    const hours = Math.round(mins / 60);
    if (hours < 24) return hours === 1 ? 'an hour ago' : hours + ' hours ago';
    const days = Math.round(hours / 24);
    if (days === 1) return 'yesterday';
    if (days < 30) return days + ' days ago';
    const months = Math.round(days / 30);
    return months <= 1 ? 'a month ago' : months + ' months ago';
  }

  function absolute(stamp) {
    const d = new Date(stamp);
    if (isNaN(d)) return '—';
    return d.toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  // Calendar days, not elapsed hours: "yesterday" has to mean yesterday's date,
  // or a row stamped 18:02 two days ago sits under "Deleted yesterday" while its
  // own label reads "2 days ago".
  function bucketOf(stamp, now) {
    const then = new Date(stamp);
    if (isNaN(then)) return 'Older';
    const ref = now || new Date();
    const a = Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), ref.getUTCDate());
    const b = Date.UTC(then.getUTCFullYear(), then.getUTCMonth(), then.getUTCDate());
    const days = Math.round((a - b) / 86400000);
    if (days <= 0) return 'Deleted today';
    if (days === 1) return 'Deleted yesterday';
    if (days < 7) return 'Earlier this week';
    if (days < 30) return 'This month';
    return 'Older';
  }
  const BUCKETS = ['Deleted today', 'Deleted yesterday', 'Earlier this week', 'This month', 'Older'];

  // ─── the list ──────────────────────────────────────────────────────────────

  function filterRows(items, filter) {
    const q = String(filter || '').trim().toLowerCase();
    if (!q) return items.slice();
    return items.filter((i) => (i.name + ' ' + i.type + ' ' + i.label + ' ' + (i.preview || ''))
      .toLowerCase().includes(q));
  }

  function rowHtml(item, selected) {
    const key = keyOf(item.type, item.id);
    const on = !!(selected && selected.has(key));
    const blocked = !!(item.restore && item.restore.blockers && item.restore.blockers.length);
    const includes = (item.includes || []).length
      ? `<div class="trash-includes">${item.includes.map((inc) => `
          <div class="trash-include">
            <span class="trash-include-type" style="color:${typeColor(inc.type)}">${h(inc.label || inc.type)}</span>
            <span>${h(inc.name)}</span>
          </div>`).join('')}</div>`
      : '';
    const chips = [
      blocked ? '<span class="trash-chip blocked">restore blocked</span>' : '',
      item.purge_eligible ? '<span class="trash-chip">30+ days</span>' : '',
      (item.includes || []).length
        ? `<span class="trash-chip count">${plural(1 + item.includes.length, 'entity', 'entities')}</span>`
        : '',
    ].filter(Boolean).join('');

    return `
  <div class="trash-row${on ? ' selected' : ''}" data-row="${h(key)}">
    <input class="trash-check" type="checkbox" data-check="${h(key)}"${on ? ' checked' : ''}
           aria-label="Select ${h(item.name)}">
    <div class="trash-main">
      <div class="trash-title-line">
        <span class="trash-type" style="color:${typeColor(item.type)}">
          <span class="trash-pip"></span>${h(item.label || item.type)}
        </span>
        <span class="trash-name">${h(item.name)}</span>
      </div>
      <div class="trash-preview">${h(item.preview || '')}</div>
      ${includes}
    </div>
    <div class="trash-meta">
      <span class="trash-age" title="${h(absolute(item.deleted_at))}">${h(relative(item.deleted_at))}</span>
      ${chips}
    </div>
  </div>`;
  }

  function groupHtml(items, selected, now) {
    const groups = new Map(BUCKETS.map((k) => [k, []]));
    items.forEach((i) => {
      const b = bucketOf(i.deleted_at, now);
      (groups.get(b) || groups.set(b, []).get(b)).push(i);
    });
    return BUCKETS.filter((k) => (groups.get(k) || []).length).map((k) => `
      <div class="trash-group">
        <div class="trash-group-title">${k}</div>
        ${groups.get(k).map((i) => rowHtml(i, selected)).join('')}
      </div>`).join('');
  }

  const BIN_ICON = `<svg width="34" height="34" viewBox="0 0 16 16" fill="none">
      <path d="M3 4.5h10M6.5 4.5V3h3v1.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
      <path d="M4.5 4.5l.6 8.2a1 1 0 0 0 1 .9h3.8a1 1 0 0 0 1-.9l.6-8.2" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
      <path d="M6.8 7v4M9.2 7v4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>
    </svg>`;

  function emptyHtml() {
    return `
    <div class="trash-empty">
      ${BIN_ICON}
      <div class="trash-empty-title">The trash is empty</div>
      <div class="trash-empty-body">Deleted scenes, characters and everything else wait here
        until you restore them or remove them for good.</div>
    </div>`;
  }

  function noMatchHtml(filter, total) {
    return `
    <div class="trash-empty">
      <div class="trash-empty-title">No deleted item matches “${h(filter)}”</div>
      <div class="trash-empty-body">Clear the filter to see all ${plural(total, 'item')}.</div>
    </div>`;
  }

  // ─── selection, and the two things you can do with it ──────────────────────

  function pruneSelection(selected, items) {
    const alive = new Set(items.map((i) => keyOf(i.type, i.id)));
    [...selected].forEach((k) => { if (!alive.has(k)) selected.delete(k); });
    return selected;
  }

  const selectedItems = () => T.items.filter((i) => T.selected.has(keyOf(i.type, i.id)));
  const blockedAmong = (items) => items.filter(
    (i) => i.restore && i.restore.blockers && i.restore.blockers.length);

  function syncActions() {
    const n = T.selected.size;
    const restore = document.getElementById('trash-restore');
    const purge = document.getElementById('trash-purge');
    const selectAll = document.getElementById('trash-select-all');
    if (!restore || !purge) return;
    const blocked = blockedAmong(selectedItems());
    restore.textContent = n ? 'Restore ' + n : 'Restore';
    purge.textContent = n ? 'Delete permanently ' + n : 'Delete permanently';
    purge.disabled = n === 0;
    // One blocked row blocks the batch — say so on the button instead of failing
    // after the click. The row's own panel is where the fix lives.
    restore.disabled = n === 0 || blocked.length > 0;
    restore.title = blocked.length
      ? blocked.map((b) => b.name).join(', ') + ' — restore the parent first'
      : 'Bring them back, exactly as they were';
    if (selectAll) selectAll.disabled = T.items.length === 0;
  }

  function renderList() {
    const host = document.getElementById('trash-list');
    const subtitle = document.getElementById('trash-subtitle');
    if (!host) return;
    const total = T.items.length;
    const entities = T.items.reduce((n, i) => n + 1 + (i.includes || []).length, 0);
    if (subtitle) {
      subtitle.textContent = total
        ? plural(total, 'item') + ' · ' + plural(entities, 'entity', 'entities')
        : 'No deleted items';
    }
    if (!total) {
      host.innerHTML = emptyHtml();
      syncActions();
      return;
    }
    const rows = filterRows(T.items, T.filter);
    if (!rows.length) {
      host.innerHTML = noMatchHtml(T.filter, total);
      syncActions();
      return;
    }
    host.innerHTML = groupHtml(rows, T.selected);
    syncActions();
  }

  async function refreshList() {
    const body = await api('/trash');
    T.items = body.items || [];
    T.countsByType = body.counts_by_type || {};
    T.entities = body.entities || 0;
    T.purgeDays = body.purge_older_than_days || 30;
    T.loadedAt = Date.now();
    pruneSelection(T.selected, T.items);
    return body;
  }

  function paintBadge(count) {
    const badge = document.getElementById('nav-trash-count');
    const btn = document.getElementById('nav-trash');
    if (badge) {
      badge.textContent = String(count);
      badge.hidden = !count;
    }
    if (btn) btn.title = count ? 'Trash — ' + plural(count, 'item') : 'Trash';
  }

  // One small GET at boot so the count is right before the tab is ever opened.
  // The trash is small by design (`dead_ids` already assumes it is).
  D.refreshTrashBadge = async function () {
    try {
      if (!slugFromHash()) return;
      const fresh = T.loadedAt && Date.now() - T.loadedAt < 4000;
      const count = fresh ? T.items.length : (await refreshList()).count;
      paintBadge(count);
    } catch (e) { /* a badge is not worth an error */ }
  };

  // ─── the preview panel ─────────────────────────────────────────────────────

  const reflected = (v) => (v && typeof v === 'object' ? (v.name || v.id || '') : v);

  function fieldRows(entity) {
    const fields = entity.fields || {};
    const rows = ['name', 'one_sentence', 'status', 'order_key', 'parent', 'location']
      .filter((k) => reflected(fields[k]))
      .map((k) => ({ key: k.replace(/_/g, ' '), value: String(reflected(fields[k])) }));
    // Scalars from `extra` (int/ext, time of day, place); the lists and maps are
    // references, and the Links card already names them in words.
    Object.entries(entity.extra || {}).forEach(([k, v]) => {
      if (typeof v === 'string' || typeof v === 'number') {
        if (k === 'one_sentence' || k === 'name') return;
        rows.push({ key: k.replace(/_/g, ' '), value: String(v) });
      }
    });
    return rows.map((r) => `
      <div class="trash-field-row">
        <div class="trash-field-key">${h(r.key)}</div>
        <div class="trash-field-value">${h(r.value).slice(0, 400)}</div>
      </div>`).join('');
  }

  function tickLine(type, id, name, kind) {
    const k = keyOf(type, id);
    return `
    <label class="trash-tick">
      <input type="checkbox" data-extra="${h(k)}"${T.pending.has(k) ? ' checked' : ''}>
      <span>${h(name)}${kind ? `<span class="trash-warn-kind">${h(kindWord(kind))}</span>` : ''}</span>
    </label>`;
  }

  const WARN_TITLES = {
    reference_in_trash: 'Links that stay hidden',
    reference_purged: 'A link that cannot come back',
    parent_trashed: 'Its parent is still in the trash',
    stranded_children: 'Children that stay hidden',
  };
  const WARN_NOTES = {
    reference_in_trash: 'They read as gaps until they come back. Tick the ones to bring back with it.',
    reference_purged: 'Gone for good: the link will read empty. There is nothing left to bring back.',
    parent_trashed: 'Tick it and it comes back in the same go, with everything of its own.',
    stranded_children: 'Deleted on their own, so they do not come back with it unless you tick them.',
  };

  function panelBodyHtml(detail) {
    const { entity, restore } = detail;

    // A structural parent in the trash: ticking it adds the parent to the same
    // call. Until it is ticked the footer's Restore is inert and says why.
    const blocker = ((restore && restore.blockers) || []).map((b) => `
      <div class="trash-panel-block">
        <div class="trash-note blocked">
          <strong>${h(b.message)}</strong>
          ${b.fix ? tickLine(b.fix.entity_type, b.fix.id, b.fix.name, '') : ''}
        </div>
      </div>`).join('');

    const warnings = Object.entries((restore && restore.warnings) || {}).map(([code, refs]) => {
      const ticked = code !== 'reference_purged';   // nothing left to bring back
      return `
      <div class="trash-panel-block">
        <div class="trash-panel-label">${h(WARN_TITLES[code] || 'Stays hidden')}</div>
        <div class="trash-note ${code === 'reference_purged' ? 'gone' : 'warn'}">
          ${refs.map((r) => (ticked
            ? tickLine(r.entity_type, r.id, r.name, r.field)
            : `<span class="trash-warn-line plain">${h(r.name)}<span class="trash-warn-kind">${h(kindWord(r.field))}</span></span>`)).join('')}
          <div class="trash-tick-note">${h(WARN_NOTES[code] || '')}</div>
        </div>
      </div>`;
    }).join('');

    const prose = Object.entries(detail.sections || {})
      .filter(([, body]) => body && body.trim() && !D.isPlaceholderSection(body))
      .sort((a, b) => (a[0] === 'Content' ? -1 : b[0] === 'Content' ? 1 : 0))
      .map(([heading, body]) => `
        <div class="trash-panel-block">
          <div class="trash-panel-label">${h(heading)}</div>
          <div class="trash-prose">${h(body)}</div>
        </div>`).join('');

    const includes = (detail.includes || []).length ? `
      <div class="trash-panel-block">
        <div class="trash-panel-label">Also deleted with it</div>
        ${detail.includes.map((inc) => `
          <div class="trash-link">
            <span class="trash-link-kind">${h(inc.label || inc.type)}</span>
            <span>${h(inc.name)}</span>
          </div>`).join('')}
        <div class="trash-footer-note" style="margin-top:6px">
          They come back with it — they went with it.
        </div>
      </div>` : '';

    const links = ((detail.relations && detail.relations.all) || []).length ? `
      <div class="trash-panel-block">
        <div class="trash-panel-label">Links</div>
        ${detail.relations.all.slice(0, 40).map((l) => `
          <div class="trash-link${l.live ? '' : ' trash-link-dead'}">
            <span class="trash-link-kind">${h(kindWord(l.kind))}</span>
            <span>${h(l.name)}</span>
          </div>`).join('')}
      </div>` : '';

    const referencedBy = (detail.referenced_by || []).length ? `
      <div class="trash-panel-block">
        <div class="trash-panel-label">Referenced by</div>
        ${detail.referenced_by.slice(0, 40).map((r) => `
          <div class="trash-link">
            <span class="trash-link-kind">${h(kindWord(r.field || r.entity_type))}</span>
            <span>${h(r.name)}</span>
          </div>`).join('')}
        <div class="trash-footer-note" style="margin-top:6px">
          These still name it, and read as having a gap until it is back.
        </div>
      </div>` : '';

    const returned = (restore && restore.returned) || {};
    const n = 1 + (returned.children || []).length;
    const whenBack = `
      <div class="trash-panel-block">
        <div class="trash-panel-label">When restored</div>
        <div class="trash-footer-note">
          ${n === 1 ? 'One entity becomes' : plural(n, 'entity', 'entities') + ' become'} visible again:
          ${returned.sections || 0} section(s), ${returned.relations || 0} link(s),
          ${(returned.referenced_by || []).length} mention(s) elsewhere.
          Nothing is rebuilt — it was only hidden.
        </div>
      </div>`;

    return blocker + `
      <div class="trash-panel-block">
        <div class="trash-panel-label">Deleted</div>
        <div class="trash-field-row">
          <div class="trash-field-value">${h(absolute(entity.deleted_at))}</div>
          <div class="trash-field-key" style="text-align:right">${h(relative(entity.deleted_at))}</div>
        </div>
      </div>
      ${fieldRows(entity)}
      ${warnings}
      ${prose}
      ${includes}
      ${links}
      ${referencedBy}
      ${whenBack}`;
  }

  function panelFooterHtml() {
    const detail = T.detail;
    if (!detail) return '';
    const pendingBlockers = ((detail.restore && detail.restore.blockers) || [])
      .filter((b) => b.fix && !T.pending.has(keyOf(b.fix.entity_type, b.fix.id)));
    const n = 1 + T.pending.size;
    const note = pendingBlockers.length
      ? `Restore “${pendingBlockers[0].fix.name}” first — tick it above.`
      : n > 1
        ? `${n} items come back together — this one, and the ${n - 1 === 1 ? 'one' : n - 1} you ticked.`
        : 'Deleting permanently cannot be undone.';
    const wide = !!T.wide;
    return `
    <span class="trash-footer-note">${h(note)}</span>
    <span class="trash-footer-actions">
      <button class="btn btn-ghost trash-widen" data-panel="widen"
              aria-pressed="${wide ? 'true' : 'false'}"
              title="${wide ? 'Narrow the preview' : 'Widen the preview'}">
        <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1.5 8h13M4.5 5 1.5 8l3 3M11.5 5l3 3-3 3"/></svg>
      </button>
      <button class="btn btn-danger btn-ghost" data-panel="purge">Delete permanently</button>
      <button class="btn btn-primary" data-panel="restore"${pendingBlockers.length ? ' disabled' : ''}>
        ${n === 1 ? 'Restore' : 'Restore ' + n}</button>
    </span>`;
  }

  function syncPanelFooter() {
    const footer = document.getElementById('panel-footer');
    if (footer) footer.innerHTML = panelFooterHtml();
  }

  async function showTrashPanel(item) {
    let detail;
    try {
      detail = await api('/trash/' + encodeURIComponent(item.type) + '/' + encodeURIComponent(item.id));
    } catch (e) {
      // Its state changed under us — the agent restored or removed it meanwhile.
      toast(e.message, 'bad');
      await reload();
      return;
    }
    T.open = keyOf(item.type, item.id);
    T.detail = detail;
    T.pending.clear();                    // a new item, a new batch
    document.getElementById('panel-type').textContent =
      (item.label || item.type) + ' · in the trash';
    document.getElementById('panel-name').textContent = item.name;
    document.getElementById('panel-edit').hidden = true;   // editing a deleted entity is refused
    document.getElementById('panel-body').innerHTML = panelBodyHtml(detail);
    const panel = document.getElementById('detail-panel');
    // The app's panel width, not the wide one: with the chat rail open a 680px
    // preview leaves the list too little room and the header wraps onto two
    // lines. Reading a screenplay is the one case that wants more, so the
    // footer's toggle offers it — and the choice lasts while the tab is open,
    // so widening once does not have to be repeated on every row.
    panel.classList.toggle('panel-wide', !!T.wide);
    const footer = document.getElementById('panel-footer');
    footer.classList.add('trash-footer');
    syncPanelFooter();
    panel.classList.add('open');
  }

  // ─── the actions ───────────────────────────────────────────────────────────

  function afterWrite() {
    // Our own write must not raise the "Project updated" banner (core.js reads
    // this guard), and the trash list is refetched because ids may have moved.
    D._ownWriteUntil = Date.now() + 8000;
    T.selected.clear();
    T.pending.clear();
  }

  async function reload() {
    if (D.reloadData) { try { await D.reloadData(); } catch (e) { /* the list is the contract */ } }
    try {
      await refreshList();
      renderList();
      paintBadge(T.items.length);
    } catch (e) { /* keep what is on screen */ }
  }

  const targetsOf = (keys) => [...keys].map((k) => {
    const [entity_type, id] = splitKey(k);
    return { entity_type, id };
  });

  function blockedDialog(err, targets) {
    const blockers = (err.body && err.body.blockers) || [];
    const refused = (err.body && err.body.refused) || blockers;
    const fixes = [];
    refused.forEach((r) => { if (r.fix) fixes.push({ entity_type: r.fix.entity_type, id: r.fix.id }); });
    const names = refused.filter((r) => r.fix).map((r) => '“' + r.fix.name + '”');
    const dlg = D.efDialog({
      kicker: 'Nothing was restored',
      title: 'A parent is still in the trash',
      bodyHtml: `<div class="trash-note blocked">
          ${refused.map((r) => `<div>${h(r.fix ? r.message : r.error || r.message || '')}</div>`).join('')}
        </div>
        <div class="trash-footer-note" style="margin-top:10px">
          ${names.length
            ? `Bringing ${names.join(' and ')} back as well puts this where the story can see it.`
            : 'Its parent no longer exists, so this would come back with nothing to hang from.'}
        </div>`,
      confirm: fixes.length ? 'Restore it as well' : 'Close',
      cancel: 'Close',
    });
    if (!fixes.length) return dlg;
    dlg.el.querySelector('[data-d=ok]').addEventListener('click', async () => {
      dlg.busy(true);
      try {
        const res = await post('/trash/restore', { targets: targets.concat(fixes) });
        dlg.close();
        afterWrite();
        await reload();
        toast('Restored ' + plural(res.restored.length, 'item') +
              ' · ' + plural(res.returned.entities, 'entity', 'entities'));
      } catch (e) {
        dlg.busy(false);
        dlg.error(h(e.message));
      }
    });
    return dlg;
  }

  async function restoreKeys(keys) {
    const targets = targetsOf(keys);
    if (!targets.length) return;
    try {
      const res = await post('/trash/restore', { targets });
      afterWrite();
      await reload();
      toast('Restored ' + plural(res.restored.length, 'item') +
            ' · ' + plural((res.returned || {}).entities || res.restored.length, 'entity', 'entities'));
    } catch (e) {
      if (e.status === 409 && e.body && (e.body.blockers || []).length) blockedDialog(e, targets);
      else { toast(e.message, 'bad'); await reload(); }
    }
  }

  function purgeBodyHtml(preview) {
    const items = preview.items || [];
    const affected = preview.affected || [];
    const rows = items.map((i) => `
      <div class="trash-link">
        <span class="trash-link-kind">${h(i.label || i.type)}</span>
        <span>${h(i.name)}</span>
      </div>`).join('');
    const also = affected.length ? `
      <div class="trash-panel-label" style="margin-top:12px">Also affected</div>
      ${affected.map((a) => `
        <div class="trash-link">
          <span class="trash-link-kind">${h(a.entity_type)}</span>
          <span>${h(a.name)}</span>
          <span style="color:var(--muted-foreground)">${a.field ? 'loses its ' + h(a.field === 'location' ? 'location' : a.field) : 'loses a reference'}</span>
        </div>`).join('')}` : '';
    return `${rows}${also}
      <div class="trash-footer-note" style="margin-top:12px">
        A backup of the database is taken first (<code>before-purge</code>), so this can be
        undone by hand. The Markdown files are removed by the next export.
      </div>`;
  }

  async function openPurgeDialog(targets) {
    let preview;
    try {
      preview = await post('/trash/purge-preview', { targets });
    } catch (e) {
      toast(e.message, 'bad');
      await reload();
      return;
    }
    const n = (preview.items || []).length;
    const dlg = D.efDialog({
      kicker: 'Cannot be undone',
      title: 'Permanently delete ' + plural(n, 'item') + '?',
      bodyHtml: purgeBodyHtml(preview),
      confirm: 'Delete ' + n + ' permanently',
      cancel: 'Keep them',
    });
    // The list is built from the SERVER's preview, never from the cached rows: a
    // row the agent restored since the page loaded must not be described as
    // about to go.
    dlg.el.querySelector('[data-d=ok]').addEventListener('click', async () => {
      dlg.busy(true);
      try {
        const res = await post('/trash/purge', { targets });
        dlg.close();
        if (T.open) D.closePanel();
        afterWrite();
        await reload();
        const name = String(res.backup || '').split('/').pop();
        toast('Permanently deleted ' + plural((res.purged || []).length, 'item') +
              (name ? ' — backup ' + name : ''));
      } catch (e) {
        dlg.busy(false);
        dlg.error(h(e.message));
      }
    });
    return dlg;
  }

  async function panelRestore() {
    const detail = T.detail;
    if (!detail) return;
    const keys = new Set([keyOf(detail.entity.type, detail.entity.id), ...T.pending]);
    const item = T.items.find((i) => keyOf(i.type, i.id) === keyOf(detail.entity.type, detail.entity.id));
    D.closePanel();
    await restoreKeys(keys);
    if (item) T.selected.delete(keyOf(item.type, item.id));
    syncActions();
  }

  async function panelPurge() {
    const detail = T.detail;
    if (!detail) return;
    await openPurgeDialog([{ entity_type: detail.entity.type, id: detail.entity.id }]);
  }

  async function purgeSelected() {
    const targets = targetsOf(T.selected);
    if (!targets.length) return;
    await openPurgeDialog(targets);
  }

  // ─── wiring ────────────────────────────────────────────────────────────────

  D.trashOpen = async function () {
    try {
      await refreshList();
      renderList();
      paintBadge(T.items.length);
    } catch (e) {
      const host = document.getElementById('trash-list');
      if (host) host.innerHTML = `<div class="trash-empty"><div class="trash-empty-title">Could not read the trash</div>
        <div class="trash-empty-body">${h(e.message)}</div></div>`;
    }
  };

  D.showTrashPanel = showTrashPanel;

  // Test seams: the render functions run in node (tests/trash_harness.js), the
  // same way the Story view's do, so markup and grouping are asserted rather
  // than grepped for.
  D.trashState = T;
  D.trashBucket = bucketOf;
  D.trashRowHtml = rowHtml;
  D.trashGroupHtml = groupHtml;
  D.trashFilterRows = filterRows;
  D.trashPruneSelection = pruneSelection;
  D.trashPanelBody = panelBodyHtml;
  D.trashPanelFooter = panelFooterHtml;
  D.trashPurgeBody = purgeBodyHtml;

  function init() {
    const list = document.getElementById('trash-list');
    if (!list) return;

    list.addEventListener('change', (e) => {
      const box = e.target.closest('[data-check]');
      if (!box) return;
      if (box.checked) T.selected.add(box.dataset.check);
      else T.selected.delete(box.dataset.check);
      renderList();
    });

    list.addEventListener('click', (e) => {
      if (e.target.closest('[data-check]')) return;
      const row = e.target.closest('[data-row]');
      if (!row) return;
      const item = T.items.find((i) => keyOf(i.type, i.id) === row.dataset.row);
      if (item) showTrashPanel(item);
    });

    const search = document.getElementById('trash-search');
    if (search) search.addEventListener('input', () => { T.filter = search.value; renderList(); });

    const selectAll = document.getElementById('trash-select-all');
    if (selectAll) selectAll.addEventListener('click', () => {
      const rows = filterRows(T.items, T.filter);
      const all = rows.length && rows.every((i) => T.selected.has(keyOf(i.type, i.id)));
      rows.forEach((i) => {
        const k = keyOf(i.type, i.id);
        if (all) T.selected.delete(k); else T.selected.add(k);
      });
      renderList();
    });

    const restore = document.getElementById('trash-restore');
    if (restore) restore.addEventListener('click', () => restoreKeys(T.selected));
    const purge = document.getElementById('trash-purge');
    if (purge) purge.addEventListener('click', purgeSelected);

    // The panel: a tick box only edits the batch; the footer is the only thing
    // that acts on it, so "what did that click do" always has an answer the
    // footer already said.
    const body = document.getElementById('panel-body');
    if (body) body.addEventListener('change', (e) => {
      const box = e.target.closest('[data-extra]');
      if (!box) return;
      if (box.checked) T.pending.add(box.dataset.extra);
      else T.pending.delete(box.dataset.extra);
      syncPanelFooter();
    });

    const footer = document.getElementById('panel-footer');
    if (footer) footer.addEventListener('click', (e) => {
      const b = e.target.closest('[data-panel]');
      if (!b || b.disabled) return;
      if (b.dataset.panel === 'restore') panelRestore();
      if (b.dataset.panel === 'purge') panelPurge();
      if (b.dataset.panel === 'widen') {
        // The one width control, and it is the reader's: narrow until asked,
        // then wide enough for a screenplay. Nothing else moves the panel.
        T.wide = !T.wide;
        document.getElementById('detail-panel').classList.toggle('panel-wide', T.wide);
        b.setAttribute('aria-pressed', T.wide ? 'true' : 'false');
        b.title = T.wide ? 'Narrow the preview' : 'Widen the preview';
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || !T.open) return;
      if (document.querySelector('.ef-backdrop.open')) return;   // a dialog owns Escape
      D.closePanel();
    });

    // Every other view: the preview may have been widened by hand, so leaving
    // the tab narrows it again (and forgets the choice) rather than handing a
    // 680px panel to the next view that opens one.
    D.onViewOpened(function (view) {
      if (view === 'trash') { D.trashOpen(); return; }
      const panel = document.getElementById('detail-panel');
      T.wide = false;
      if (panel) panel.classList.remove('panel-wide');
      const footerEl = document.getElementById('panel-footer');
      if (footerEl) footerEl.classList.remove('trash-footer');
      T.open = null;
      T.detail = null;
    });

    // Boot and every `reloadData` rebuild the story; the badge follows, so the
    // count is never stale after a restore, a purge or a delete from the form.
    const origInit = D.initStory;
    if (origInit) {
      D.initStory = function (data) {
        origInit.call(D, data);
        D.refreshTrashBadge();
      };
    }
  }

  init();
})(window.DASH);
