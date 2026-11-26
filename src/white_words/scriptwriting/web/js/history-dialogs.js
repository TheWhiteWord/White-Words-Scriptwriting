window.DASH = window.DASH || {};

// Dialog pieces the projects page and the writing view's draft chip share. They sit on
// DASH.efDialog, so a dialog here looks and behaves like every other dialog in the app.
(function (D) {
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const toast = (m, kind) => (D.efToast ? D.efToast(m, kind) : console.warn(m));

  const field = (label, html, help) => '<label class="ef-field"><span class="ef-label">' + esc(label) + '</span>' + html + (help ? '<span class="ef-help">' + esc(help) + '</span>' : '') + '</label>';
  const val = (d, name) => { const el = d.el.querySelector('[data-f="' + name + '"]'); return el ? el.value.trim() : ''; };
  const checked = (d, name) => { const el = d.el.querySelector('[data-f="' + name + '"]'); return !!(el && el.checked); };

  // Run an action inside a dialog: busy while it works, the server's sentence on refusal.
  async function attempt(d, fn) {
    d.error('');
    d.busy(true);
    try { await fn(); } catch (e) { d.error(esc(e.message)); d.busy(false); return false; }
    return true;
  }

  // Save the current branch's open draft. `next` is the number an unnamed draft gets.
  function saveDraft(o) {
    const d = D.efDialog({
      kicker: 'Save draft', title: o.branchName ? 'Save “' + o.branchName + '” as a draft' : 'Save the first draft', confirm: 'Save draft',
      bodyHtml: field('Name', '<input class="ef-input" data-f="label" maxlength="80" placeholder="Draft ' + esc(o.next) + '">', 'Optional.')
        + field('Note', '<textarea class="ef-input ef-area" data-f="note" rows="3" placeholder="What is this version for?"></textarea>'),
      onConfirm: async (dlg) => {
        let saved;
        if (await attempt(dlg, async () => { saved = await D.historyApi(o.slug, 'POST', '/snapshots', { label: val(dlg, 'label') || null, note: val(dlg, 'note') }); })) {
          dlg.close();
          toast('Saved “' + saved.label + '”.');
          if (o.onSaved) o.onSaved(saved);
        }
      },
    });
    d.el.querySelector('[data-f="label"]').focus();
    return d;
  }

  D.historyDialogs = { esc, toast, field, val, checked, attempt, saveDraft };
})(window.DASH);
