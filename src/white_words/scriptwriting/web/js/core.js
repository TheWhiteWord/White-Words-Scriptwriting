// ─── Boot ─────────────────────────────────────────────────────────────────────
window.DASH = window.DASH || {};

let story = null;

let network = null;


DASH.askAgent = function(text) {
  try { navigator.clipboard.writeText(text); } catch (e) {}
  alert('Prompt copied to clipboard. Paste it into Hermes chat.');
};

document.addEventListener('click', function(e){
  const b = e.target && e.target.closest && e.target.closest('[data-hermes-send]');
  if (b) { e.preventDefault(); DASH.askAgent(b.getAttribute('data-hermes-send')); }
});
// ─── Loading overlay ──────────────────────────────────────────────────────────
// Every mark draws itself in, so hiding the overlay the moment the data lands
// cuts the stroke off halfway — on a local machine that is a 60 ms flash of a
// barely started animation. Each show records the earliest time the overlay may
// go away, and hideLoading waits out whatever is left.
// The floors come from the files' own timelines: the typewriter splash draws the
// W by 1.5 s, finishes typing the name at 3.05 s and settles its caret at 4.1 s,
// so 4.3 s shows it whole; the bare W is drawn by 1.5 s.
DASH.LOADING_FLOOR_MS = { initial: 4300, project: 1700, refresh: 1700, picker: 0 };
DASH.MARK_SELECTOR = { initial: '.loading-initial', project: '.loading-w', refresh: '.loading-w' };

// A mark that has already played keeps its finished frame when re-shown: the
// animation timeline belongs to the decoded image document, not to the element,
// so display:none then block gives you the static end state. A fresh query
// string makes it a new document, and the stroke draws again from the start.
// The picker kind has no mark at all — going back should not cost an animation.
DASH.rewindMark = function(el, kind) {
  const sel = DASH.MARK_SELECTOR[kind];
  if (!sel) return;
  const img = el.querySelector(sel);
  if (!img) return;
  const base = (img.getAttribute('src') || '').split('?')[0];
  DASH._markSeq = (DASH._markSeq || 0) + 1;
  img.src = base + '?r=' + DASH._markSeq;
};

DASH.showLoading = function(kind) {
  const el = document.getElementById('loading-screen');
  if (!el) return;
  const k = DASH.LOADING_FLOOR_MS[kind] ? kind : 'initial';
  el.classList.remove('initial', 'project', 'refresh');
  el.classList.add(k);
  el.style.display = 'flex';
  // Only ever reached for in-app shows; the first paint starts its own mark.
  DASH.rewindMark(el, k);
  DASH._loadingUntil = Date.now() + DASH.LOADING_FLOOR_MS[k];
};

// Only the project kind shows a caption, and it names the story being loaded.
// The name sits behind /api/projects, so it lands a moment after first paint —
// an empty caption until then is better than a placeholder that has to change.
DASH.setLoadingCaption = function(text) {
  const el = document.getElementById('loading-screen');
  const cap = el && el.querySelector('.loading-text');
  if (!cap || el.style.display === 'none') return;
  cap.textContent = text || '';
};

DASH.loadingProjectName = async function(slug) {
  try {
    const res = await fetch('/api/projects');
    const data = await res.json();
    const project = (data.projects || []).find(function(p) { return p.slug === slug; });
    if (project && project.name) DASH.setLoadingCaption('Loading ' + project.name + '…');
  } catch (e) { /* the caption is decoration; the load itself is unaffected */ }
};

// force: the error screen should never wait on an animation.
// Returns a promise that settles when the overlay is actually gone, for callers
// that replace #app's markup (the picker would otherwise destroy the overlay
// before the floor elapses).
DASH.hideLoading = function(force) {
  const el = document.getElementById('loading-screen');
  if (!el) return Promise.resolve();
  if (DASH._loadingTimer) { clearTimeout(DASH._loadingTimer); DASH._loadingTimer = null; }
  let reduced = false;
  try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}
  // First paint never calls showLoading — the overlay is in the markup, with a
  // kind class index.html sets from the URL — so take the floor from that class
  // and count from the stamp taken as the overlay was parsed.
  let kind = 'initial';
  for (const k in DASH.LOADING_FLOOR_MS) if (el.classList.contains(k)) kind = k;
  const until = DASH._loadingUntil || ((window.__wwLoadingStart || Date.now()) + DASH.LOADING_FLOOR_MS[kind]);
  const wait = (force || reduced) ? 0 : Math.max(0, until - Date.now());
  if (!wait) { el.style.display = 'none'; return Promise.resolve(); }
  return new Promise(function(resolve) {
    DASH._loadingTimer = setTimeout(function() {
      DASH._loadingTimer = null;
      el.style.display = 'none';
      resolve();
    }, wait);
  });
};

// The twelve rail marks ship as one sprite. An external <use href="file#id"> is
// not reliable outside Chrome, so the symbols are fetched once and put in the
// document, where <use href="#id"> resolves in every browser.
DASH.loadNavSprite = async function() {
  try {
    const res = await fetch('icons/nav-sprite.svg');
    if (!res.ok) return;
    const doc = new DOMParser().parseFromString(await res.text(), 'image/svg+xml');
    if (!doc.querySelector('symbol')) return;
    const host = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    host.setAttribute('aria-hidden', 'true');
    host.setAttribute('style', 'position:absolute;width:0;height:0;overflow:hidden');
    doc.querySelectorAll('symbol').forEach(function(s) { host.appendChild(document.importNode(s, true)); });
    document.body.insertBefore(host, document.body.firstChild);
  } catch (e) { /* a missing sprite costs the glyphs, not the dashboard */ }
};

// Fetch a project and rebuild every view from it. Shared by boot and by the
// update banner's refresh, which re-reads in place instead of reloading.
DASH.loadDashboard = async function(slug) {
  const res = await fetch('/api/projects/' + encodeURIComponent(slug) + '/dashboard');
  if (!res.ok) { DASH.showError(); return false; }
  const data = await res.json();
  window.__STORY_DATA__ = data.story_data;
  window.__SECTIONS__ = data.sections;
  window.__SCREENPLAY_STATS__ = data.screenplay_stats;
  window.__STRUCTURAL_STATS__ = data.structural_stats;
  if (DASH.network) { try { DASH.network.destroy(); } catch (e) { /* already gone */ } DASH.network = null; }
  DASH.hideLoading();
  DASH.initStory(data.story_data);
  DASH.watchUpdates(slug);
  DASH.draftChip.mount(slug);
  return true;
};

DASH.boot = async function() {
  try {
    await DASH.loadNavSprite();   // the rail's glyphs, before anything is drawn
    const m = (location.hash || '').match(/^#\/p\/([^/?]+)/);
    if (!m) {
      await DASH.showPicker();
      return;
    }
    const slug = decodeURIComponent(m[1]);
    DASH.loadingProjectName(slug);   // fills the caption while the payload is in flight
    if (!await DASH.loadDashboard(slug)) return;
    if (DASH.routeEditor) DASH.routeEditor();   // a reload on #/p/<slug>/scene/<id>/edit reopens the editor
  } catch (e) {
    DASH.showError();
  }
};

DASH.watchUpdates = function(slug) {
  try {
    if (DASH._es) DASH._es.close();
    const es = new EventSource('/api/projects/' + encodeURIComponent(slug) + '/events');
    DASH._es = es;
    es.addEventListener('update', function() {
      DASH.showUpdateIndicator(slug);
      DASH.draftChip.refresh();
    });
    es.onerror = function() { /* auto-reconnect by browser */ };
  } catch (e) {}
};

DASH.showUpdateIndicator = function(slug) {
  let el = document.getElementById('sa-update-banner');
  if (!el) {
    el = document.createElement('div');
    el.id = 'sa-update-banner';
    el.style.cssText = 'position:fixed;top:8px;right:8px;background:#222;color:#fff;padding:8px 12px;border-radius:6px;z-index:9999;font-size:13px;';
    el.innerHTML = 'Project updated <button id="sa-refresh-btn">Refresh</button>';
    document.body.appendChild(el);
    document.getElementById('sa-refresh-btn').onclick = function() { DASH.refreshProject(slug); };
  }
  el.style.display = 'block';
};

// Re-read the project in place, under a scrim. Reloading the page threw away the
// open view for what is only new data; the scrim keeps the app visible, and the
// mark still draws out so a refresh reads as something happening.
DASH.refreshProject = async function(slug) {
  DASH.hideUpdateIndicator();
  DASH.showLoading('refresh');
  try { await DASH.loadDashboard(slug); } catch (e) { DASH.showError(); }
};

DASH.hideUpdateIndicator = function() {
  const el = document.getElementById('sa-update-banner');
  if (el) el.remove();
};

DASH.showError = function() {
  DASH.hideLoading(true);
  document.getElementById('error-screen').style.display = 'flex';
}

DASH.normalise = function(data) {
  const d = JSON.parse(JSON.stringify(data)); // deep clone

  // Characters
  (d.characters || []).forEach(c => {
    // story_role → role
    if (c.story_role && !c.role) c.role = c.story_role;
    // goals_short / goals_long arrive flat, from the DB and from the sample
    // alike. There is no nested `goals` object anywhere in the system.
    // knowledge: string[] → join for display (keep array for panel)
    if (Array.isArray(c.knowledge)) {
      c._knowledge_arr = c.knowledge;
      c.knowledge = c.knowledge.join(' · ');
    }
    // scenes: [{id, heading}] → map to scene IDs (prefer id match)
    if (Array.isArray(c.scenes) && c.scenes.length && typeof c.scenes[0] === 'object') {
      c._scene_objs = c.scenes;
      c.scenes = c.scenes.map(s => {
        const found = (d.scenes || []).find(sc =>
          String(sc.id) === String(s.id) ||  // match by slug id (preferred)
          sc.heading === s.heading ||          // fallback: heading match
          (sc.heading || '').includes(s.heading || '__NOMATCH__')  // fallback: fuzzy
        );
        return found ? String(found.id) : (s.heading || String(s.id));
      });
    } else {
      // ensure they're strings for consistent lookup
      c.scenes = (c.scenes || []).map(s => String(s));
    }
  });

  // Scenes: ensure id is string, title exists, normalise character/location arrays
  (d.scenes || []).forEach(s => {
    s.id = String(s.id);
    s.title = s.title || s.id;  // ensure title exists
    s.characters = (s.characters || []).map(String);
    // locations: normalize from location (string) or locations (array)
    s.locations = DASH.normalizeLocs(s.locations || s.location);
    s.plots = (s.plots || []);
  });

  // Plots: role fields already normalized by backend to [{scene_id, description}]
  (d.plots || []).forEach(pl => {
    pl.characters = (pl.characters || []).map(String);
  });

  // Locations: scene refs arrive as {id, title, heading} (or bare heading
  // strings). Keep the heading: it is how the location card and panel label a
  // scene, and how `findLocation` resolves a heading back to its location.
  (d.locations || []).forEach(loc => {
    if (!loc._scene_headings && Array.isArray(loc.scenes)) {
      loc._scene_headings = loc.scenes
        .map(s => (typeof s === 'string' ? s : (s && s.heading) || ''))
        .filter(Boolean);
    }
  });

  d.worlds = d.worlds || [];
  d.values = d.values || [];
  d.story_memory = d.story_memory || { status: "ready", usage: "0/3000", counts: {}, categories: {} };
  d.story_memory.categories = d.story_memory.categories || {};

  return d;
}

DASH.initStory = function(data) {
  DASH.story = DASH.normalise(data);
  DASH.story.characters = DASH.story.characters || [];
  DASH.story.locations  = DASH.story.locations  || [];
  DASH.story.plots      = DASH.story.plots      || [];
  DASH.story.scenes     = DASH.story.scenes     || [];
  DASH.story.worlds     = DASH.story.worlds     || [];
  DASH.story.values     = DASH.story.values     || [];
  DASH.story.story_memory = DASH.story.story_memory || {};
  DASH.story.relationships = DASH.story.relationships || [];

  DASH.hideLoading();

  DASH.buildGraphView();
  DASH.buildScenesView();
  DASH.buildLocationsView();
  DASH.buildPlotsView();
  DASH.buildRelationshipsView();
  DASH.buildWorldsView();
  DASH.buildStoryView();
  DASH.buildValuesView();
  DASH.buildScriptView();
}
