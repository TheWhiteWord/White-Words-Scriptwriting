window.DASH = window.DASH || {};

// One call under /api/projects/<slug>/history. A refusal throws an Error carrying the
// server's own sentence, so a dialog can show it as written; `code` and `detail` hold
// the rest of the envelope.
DASH.historyApi = async function (slug, method, path, body) {
  const res = await fetch('/api/projects/' + encodeURIComponent(slug) + '/history' + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-White-Words': '1' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error((data.error && data.error.message) || res.statusText);
    err.status = res.status;
    err.code = data.error && data.error.code;
    err.detail = data.error || {};
    throw err;
  }
  return data;
};

// Load a project in the writing view. The first-paint script in index.html reads the
// hash, so the reload both selects the project and shows the right loading mark.
DASH.openProject = function (slug) {
  location.hash = '#/p/' + encodeURIComponent(slug);
  location.reload();
};
