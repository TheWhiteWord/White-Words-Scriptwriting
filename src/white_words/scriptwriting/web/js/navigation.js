window.DASH = window.DASH || {};

let sidebarExpanded = false;

let currentView = 'graph';

DASH._viewOpenedHooks = [];
DASH.onViewOpened = function(fn) { DASH._viewOpenedHooks.push(fn); };

DASH.valueGraphLink = function(target) {
  const isPlot = target !== 'story';
  const state = `DASH.valueGraphState.tab='${isPlot ? 'plot' : 'story'}';DASH.valueGraphState.plot=${isPlot ? `'${target}'` : 'null'};`;
  return `<button class="vg-link" onclick="${state}DASH.switchView('values', document.querySelector('[data-view=values]'));" title="View graph">
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 12l3-4 3 2 3-6 3 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </button>`;
};

DASH.switchView = function(view, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn[data-view]').forEach(b => b.classList.remove('active'));
  document.getElementById(view + '-view').classList.add('active');
  btn.classList.add('active');
  DASH.currentView = view;
  if (view === 'graph' && DASH.network) {
    DASH.network.redraw();
    DASH.network.fit();
  }
  DASH._viewOpenedHooks.forEach(fn => fn(view));
  DASH.closePanel();
}

DASH.toggleSidebar = function() {
  DASH.sidebarExpanded = !DASH.sidebarExpanded;
  document.getElementById('sidebar').classList.toggle('expanded', DASH.sidebarExpanded);
}

// Back to the projects list. The picker rewrites #app's markup, so it can only
// ever be a boot state: clear the project from the URL and start the app over.
// The flag tells the next boot to skip the typewriter, since this is a step back
// through the app rather than an app open.
DASH.openProjects = function() {
  try { sessionStorage.setItem('ww:picker', '1'); } catch (e) { /* private mode */ }
  history.replaceState(null, '', location.pathname);
  location.reload();
}

DASH.refreshIndex = function() {
  DASH.showLoading('refresh');
  if (DASH.network) { DASH.network.destroy(); DASH.network = null; }
  setTimeout(DASH.boot, 50);
}

DASH.switchGraphTab = function(tab) {
  document.querySelectorAll('.graph-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.graph-tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + tab)?.classList.add('active');
  const content = document.getElementById('graph-tab-' + tab);
  if (content) {
    content.classList.add('active');
    content.style.display = '';
  }
  const netLegend = document.getElementById('graph-legend');
  if (netLegend) netLegend.style.display = (tab === 'network') ? '' : 'none';
}

DASH._origSwitchView = DASH.switchView;
