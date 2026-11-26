window.DASH = window.DASH || {};

// The draft chip: in every view's header, which branch and draft the project is on, how
// far it has moved since, and a Save draft button. Clicking the chip goes to the projects
// page with this project's history open. `render` is pure; the rest keeps the chip true.
(function (D) {
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  function render(st) {
    if (!st) return '';
    const go = ' data-dc="projects" title="Open the projects page: drafts, branches and history"';
    if (!st.branch_count) {
      return '<button class="dc-chip none"' + go + '>No drafts yet</button>'
        + '<button class="btn dc-save" data-dc="save">Save first draft</button>';
    }
    const n = st.changes_since_save || 0;
    const where = st.current_branch + ' · ' + st.current_draft;
    const label = n ? where + ' · ' + n + (n === 1 ? ' change' : ' changes') : where;
    return '<button class="dc-chip' + (n ? ' changed' : '') + '"' + go + ' aria-label="Draft: ' + esc(label) + '">' + esc(label) + '</button>'
      + '<button class="btn dc-save" data-dc="save"' + (n ? '' : ' disabled title="Nothing has changed since ' + esc(st.current_draft) + '."') + '>Save draft</button>';
  }

  D.draftChip = { render };

  if (typeof document === 'undefined') return;

  const S = { slug: null, status: null, timer: 0, wrapped: false };

  function paint() {
    document.querySelectorAll('.view-header-actions').forEach((actions) => {
      let dc = actions.querySelector(':scope > .dc');
      if (!dc) {
        dc = document.createElement('div');
        dc.className = 'dc';
        actions.insertBefore(dc, actions.firstChild);
      }
      dc.innerHTML = render(S.status);
    });
  }

  async function refresh() {
    if (!S.slug) return;
    try { S.status = await D.historyApi(S.slug, 'GET', '/status'); } catch (e) { S.status = null; }
    paint();
  }

  const soon = () => { clearTimeout(S.timer); S.timer = setTimeout(refresh, 400); };

  // Four modules send writes, each with its own helper, so the one place that sees them
  // all is fetch. A successful write to this project (chat traffic aside) moves the
  // chip's count, so it is re-read.
  function watchWrites() {
    if (S.wrapped) return;
    S.wrapped = true;
    const native = window.fetch.bind(window);
    window.fetch = async function (input, init) {
      const res = await native(input, init);
      try {
        const method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const mine = S.slug && url.indexOf('/api/projects/' + encodeURIComponent(S.slug) + '/') !== -1;
        if (method !== 'GET' && res.ok && mine && url.indexOf('/chat') === -1) soon();
      } catch (e) { /* the chip is a courtesy; a write is never held up for it */ }
      return res;
    };
  }

  function onClick(e) {
    const t = e.target.closest('[data-dc]');
    if (!t || t.disabled) return;
    if (t.dataset.dc === 'projects') {
      try { sessionStorage.setItem('ww:expand', S.slug); } catch (err) { /* private mode */ }
      D.openProjects();
    } else if (t.dataset.dc === 'save' && S.status) {
      D.historyDialogs.saveDraft({ slug: S.slug, branchName: S.status.current_branch, next: S.status.next_draft_number, onSaved: refresh });
    }
  }

  // Called after every dashboard load; the headers are static markup, so painting is idempotent.
  D.draftChip.mount = function (slug) {
    S.slug = slug;
    if (!S.wrapped) {
      watchWrites();
      document.addEventListener('click', onClick);
      window.addEventListener('focus', soon);
      D.onViewOpened(soon);
    }
    paint();
    refresh();
  };
  D.draftChip.refresh = refresh;
})(window.DASH);
