'use strict';
// ===========================================================================
// Plugfile — Rules Monitor admin panel. Reads the login-gated
// GET /api/rules/status and renders the latest RRC rules-watch snapshot,
// detected changes, and (if present) Claude's feature suggestions.
// ===========================================================================
(function () {
  const el = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function authHeaders() {
    return (window.PlugfileAuth && window.PlugfileAuth.authHeaders &&
            window.PlugfileAuth.authHeaders()) || {};
  }
  function authEnabled() {
    return !!(window.PlugfileAuth && window.PlugfileAuth.isEnabled &&
              window.PlugfileAuth.isEnabled());
  }
  function signedIn() {
    return !!(window.PlugfileAuth && window.PlugfileAuth.user &&
              window.PlugfileAuth.user());
  }

  function badge(type) {
    const cls = (type === 'changed' || type === 'new') ? 'fail'
              : (type === 'error') ? 'warn' : 'pass';
    return `<span class="verdict-conf" style="color:var(--${cls === 'fail' ? 'error' : cls === 'warn' ? 'warn' : 'success'})">${esc(type)}</span>`;
  }

  function render(data) {
    const box = el('rules-body');
    if (!data) { box.innerHTML = ''; return; }

    if (!data.available) {
      box.innerHTML = `<div class="result-card"><div class="hint">${esc(data.message || 'No snapshot yet.')}</div>
        <div class="aor-note" style="margin-top:8px">Run <code>plugfile-rules-watch --seed</code> (or the scheduled job) to create the baseline.</div></div>`;
      return;
    }

    const lr = data.last_report;
    let html = '';

    // Summary
    if (lr) {
      const s = lr.summary || {};
      const cls = (s.changed ? 'fail' : (s.errors ? 'warn' : 'pass'));
      html += `<div class="verdict ${cls}"><div class="verdict-head">`
        + `${s.changed ? '⚠ ' + s.changed + ' change(s) detected' : '✓ No changes at last check'}`
        + `<span class="verdict-conf">${esc(lr.generated_at || '')}</span></div>`;
      html += `<div class="aor-note">${s.changed || 0} changed · ${s.errors || 0} error(s) · ${s.total || 0} target(s) monitored${lr.seeded ? ' · (baseline seeded)' : ''}</div></div>`;

      const changed = (lr.changes || []).filter(c => ['changed', 'new', 'error'].includes(c.change_type));
      if (changed.length) {
        html += `<h3 class="aor-h3">Detected changes</h3>`;
        html += changed.map(c => `<div class="aor-finding ${c.change_type === 'error' ? 'inradius' : 'iso'}">
          <div class="aor-finding-head"><span>${esc(c.label)}</span>${badge(c.change_type)}</div>
          <div class="aor-note"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a></div>
          <div class="aor-note">maps to: ${esc(c.category)}${c.error ? ' · ' + esc(c.error) : ''}</div>
          ${c.diff ? `<pre class="rules-diff">${esc(c.diff).slice(0, 4000)}</pre>` : ''}
        </div>`).join('');
      }

      if (lr.suggestions) {
        html += `<h3 class="aor-h3">Suggestions</h3><pre class="rules-diff">${esc(lr.suggestions).slice(0, 8000)}</pre>`;
      }
    }

    // Targets table
    const targets = data.targets || {};
    html += `<h3 class="aor-h3">Monitored targets</h3>`;
    html += Object.keys(targets).map(k => {
      const t = targets[k];
      const ok = t.status === 200;
      return `<div class="result-row"><span class="rlabel">${esc(k)}</span>
        <span>${ok ? '✓' : '⚠'} HTTP ${esc(t.status)} · ${esc(t.fetched_at || '—')} · <code>${esc(t.hash || '')}</code></span></div>`;
    }).join('') || '<div class="hint">No targets recorded.</div>';
    html += `<div class="aor-note" style="margin-top:8px">Snapshot saved: ${esc(data.saved_at || '—')}</div>`;

    box.innerHTML = html;
  }

  async function refresh() {
    const box = el('rules-body');
    if (authEnabled() && !signedIn()) {
      box.innerHTML = `<div class="result-card"><div class="hint">Sign in (top right) to view the rules monitor.</div></div>`;
      return;
    }
    box.innerHTML = `<div class="hint">Loading…</div>`;
    try {
      const res = await fetch('/api/rules/status', { headers: { ...authHeaders() } });
      if (res.status === 401) {
        box.innerHTML = `<div class="result-card"><div class="hint">Sign in (top right) to view the rules monitor.</div></div>`;
        return;
      }
      if (!res.ok) throw new Error('HTTP ' + res.status);
      render(await res.json());
    } catch (e) {
      box.innerHTML = `<div class="result-card"><div class="warn-item">Could not load rules status: ${esc(e.message)}</div></div>`;
    }
  }

  window.PlugfileRules = { refresh };
  document.addEventListener('DOMContentLoaded', () => {
    el('rules-refresh').addEventListener('click', refresh);
    refresh();
  });
})();
