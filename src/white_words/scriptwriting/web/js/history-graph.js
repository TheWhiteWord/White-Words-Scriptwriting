window.DASH = window.DASH || {};

// The branch graph: one lane per branch, one node per draft, and at the end of each lane
// a hollow tip for the branch's open draft. `layout` is pure and returns what to draw;
// `svg` turns that into markup. Both read `GET /history/` as it is.
(function (D) {
  const DX = 116;
  const DY = 72;
  const LABEL_W = 112;
  const X0 = 64;
  const PAD_Y = 30;

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

  function layout(summary) {
    const snaps = {};
    (summary.snapshots || []).forEach((s) => { snaps[s.id] = s; });
    // Oldest branch first, and on a tie (timestamps are whole seconds) the branch that
    // holds the project's first draft, so the trunk is always the top lane.
    const root = (summary.snapshots || []).find((s) => !(s.parents || []).length);
    const rank = (b) => (root && b.id === root.branch_id ? 0 : 1);
    const branches = (summary.branches || []).slice().sort((a, b) =>
      String(a.created_at).localeCompare(String(b.created_at)) || rank(a) - rank(b) || String(a.name).localeCompare(String(b.name)));
    const parentsOf = (id) => ((snaps[id] && snaps[id].parents) || []).filter((p) => snaps[p]);

    const col = {};
    const colOf = (id) => {
      if (col[id] == null) {
        const ps = parentsOf(id);
        col[id] = ps.length ? Math.max.apply(null, ps.map(colOf)) + 1 : 0;
      }
      return col[id];
    };
    Object.keys(snaps).forEach(colOf);

    const lane = {};
    branches.forEach((b, i) => { lane[b.id] = i; });
    // A draft saved on a branch that was later deleted still sits on the lane of a
    // branch whose history reaches it.
    const laneOfDraft = (s) => {
      if (lane[s.branch_id] != null) return lane[s.branch_id];
      for (const b of branches) {
        const seen = new Set();
        const stack = [b.base_snapshot_id];
        while (stack.length) {
          const id = stack.pop();
          if (id === s.id) return lane[b.id];
          if (!seen.has(id)) { seen.add(id); parentsOf(id).forEach((p) => stack.push(p)); }
        }
      }
      return 0;
    };

    const at = (c, l) => ({ x: X0 + c * DX, y: PAD_Y + l * DY });
    const nodes = {};
    (summary.snapshots || []).forEach((s) => {
      nodes['s:' + s.id] = Object.assign({ kind: 'draft', id: s.id, label: s.label, note: s.note || '', branch: s.branch_id }, at(col[s.id], laneOfDraft(s)));
    });
    const heads = summary.head || {};
    branches.forEach((b) => {
      const baseCol = col[b.base_snapshot_id] == null ? 0 : col[b.base_snapshot_id];
      const h = heads[b.id] || {};
      nodes['t:' + b.id] = Object.assign({ kind: 'tip', id: b.id, label: b.name, branch: b.id, changes: h.changes || 0, changed: !!h.changed, current: !!b.is_current }, at(baseCol + 1, lane[b.id]));
    });

    const edges = [];
    const add = (from, to, kind) => { if (nodes[from] && nodes[to]) edges.push({ from: nodes[from], to: nodes[to], kind }); };
    (summary.snapshots || []).forEach((s) => {
      parentsOf(s.id).forEach((p, i) => add('s:' + p, 's:' + s.id, i === 0 ? 'parent' : 'merge'));
    });
    branches.forEach((b) => {
      add('s:' + b.base_snapshot_id, 't:' + b.id, 'tip');
      (b.pending_merge_parents || []).forEach((p) => add('s:' + p, 't:' + b.id, 'pending'));
    });
    // A merge declared complete but not yet saved is a pending edge already.
    const seen = new Set();
    branches.forEach((b) => (b.pending_merge_parents || []).forEach((p) => seen.add('s:' + p + '>' + b.id)));
    (summary.picked_from || []).forEach((p) => {
      const src = p.source || {};
      const from = src.kind === 'branch' ? 't:' + src.id : 's:' + src.id;
      const key = from + '>' + p.branch;
      if (!seen.has(key)) { seen.add(key); add(from, 't:' + p.branch, 'pick'); }
    });

    const all = Object.keys(nodes).map((k) => nodes[k]);
    const width = Math.max.apply(null, all.map((n) => n.x).concat([X0])) + DX * 0.6;
    const height = PAD_Y * 2 + Math.max(0, branches.length - 1) * DY + 34;
    return { nodes: all, edges, lanes: branches.map((b, i) => ({ id: b.id, name: b.name, current: !!b.is_current, y: PAD_Y + i * DY })), width, height };
  }

  function edgePath(a, b) {
    if (Math.abs(a.y - b.y) < 1) return 'M' + a.x + ' ' + a.y + 'H' + b.x;
    const c = Math.max(40, Math.abs(b.x - a.x) / 2);
    return 'M' + a.x + ' ' + a.y + 'C' + (a.x + c) + ' ' + a.y + ' ' + (b.x - c) + ' ' + b.y + ' ' + b.x + ' ' + b.y;
  }

  function plural(n, w) { return n + ' ' + w + (n === 1 ? '' : /(ch|sh|s|x)$/.test(w) ? 'es' : 's'); }

  function svg(summary) {
    const g = layout(summary);
    const edges = g.edges.map((e) => '<path class="hg-edge ' + e.kind + '" d="' + edgePath(e.from, e.to) + '"/>').join('');
    const lanes = g.lanes.map((l) => '<text class="hg-lane' + (l.current ? ' current' : '') + '" x="12" y="' + (l.y + 4) + '"><title>' + esc(l.name) + '</title>' + esc(clip(l.name, 14)) + '</text>').join('');
    const nodes = g.nodes.map((n) => {
      if (n.kind === 'draft') {
        return '<g class="hg-node" data-snapshot="' + esc(n.id) + '"><title>' + esc(n.label + (n.note ? ' — ' + n.note : '')) + '</title>'
          + '<circle class="hg-dot" cx="' + n.x + '" cy="' + n.y + '" r="9"/>'
          + '<text class="hg-label" x="' + n.x + '" y="' + (n.y + 28) + '" text-anchor="middle">' + esc(clip(n.label, 18)) + '</text></g>';
      }
      const state = n.changed ? plural(n.changes, 'change') : 'no changes';
      return '<g class="hg-node hg-tipnode" data-branch="' + esc(n.id) + '"><title>' + esc(n.label + ' — open draft, ' + state) + '</title>'
        + '<circle class="hg-tip' + (n.changed ? ' changed' : '') + '" cx="' + n.x + '" cy="' + n.y + '" r="8"/>'
        + '<text class="hg-label muted" x="' + n.x + '" y="' + (n.y + 26) + '" text-anchor="middle">in progress</text>'
        + '<text class="hg-label muted small' + (n.changed ? ' changed' : '') + '" x="' + n.x + '" y="' + (n.y + 40) + '" text-anchor="middle">' + esc(state) + '</text></g>';
    }).join('');
    const words = g.nodes.filter((n) => n.kind === 'draft').length;
    const h = Math.ceil(g.height);
    // Branch names sit in their own fixed column so they stay put while the drafts scroll.
    return '<div class="hg-wrap"><svg class="hg-lanes" width="' + LABEL_W + '" height="' + h + '" aria-hidden="true">' + lanes + '</svg>'
      + '<div class="hg-scroll"><svg class="hg" width="' + Math.ceil(g.width) + '" height="' + h + '" viewBox="0 0 ' + Math.ceil(g.width) + ' ' + h + '" role="img" aria-label="Branch graph: ' + plural(g.lanes.length, 'branch') + ', ' + plural(words, 'draft') + '">'
      + '<g>' + edges + '</g><g>' + nodes + '</g></svg></div></div>';
  }

  D.historyGraph = { layout, svg, DX };
})(window.DASH);
