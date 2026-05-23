'use strict';
// ===========================================================================
// Plugfile save / resume — persists wizard state to Supabase (per-user, RLS).
//
//   * Requires a signed-in user (window.PlugfileAuth). In open mode or when
//     signed out, the whole UI is hidden — a complete no-op.
//   * Each wizard page exposes window.PlugfileWizard = { formType, getState(),
//     restore(data), title() }. This module reads/writes those.
//   * Data isolation is enforced by Row-Level Security in Postgres (see
//     supabase/migrations/0001_filings.sql), not by this client code.
// ===========================================================================
(function () {
  const ST = { currentId: null };

  function client() {
    return window.PlugfileAuth && window.PlugfileAuth.client
      ? window.PlugfileAuth.client() : null;
  }
  function signedIn() {
    return !!(window.PlugfileAuth && window.PlugfileAuth.user
      && window.PlugfileAuth.user());
  }
  function wizard() { return window.PlugfileWizard || null; }

  function note(msg, ok) {
    // Reuse the host page's toast if present, else a minimal fallback.
    if (typeof window.toast === 'function') { window.toast(msg, ok ? 'ok' : 'error'); return; }
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);`
      + `background:${ok ? '#22c55e' : '#ef4444'};color:#fff;padding:12px 20px;`
      + `border-radius:10px;font-size:.88rem;font-weight:600;z-index:999;`;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  async function save() {
    const c = client(); const w = wizard();
    if (!c || !w) return;
    const st = w.getState();
    const row = {
      form_type: w.formType,
      api_number: st.api || null,
      title: (w.title && w.title()) || `${w.formType.toUpperCase()} draft`,
      step: st.step || 1,
      data: st,
    };
    try {
      let res;
      if (ST.currentId) {
        res = await c.from('filings').update(row).eq('id', ST.currentId).select().single();
      } else {
        res = await c.from('filings').insert(row).select().single();
      }
      if (res.error) throw res.error;
      ST.currentId = res.data.id;
      note('Filing saved.', true);
      refresh();
    } catch (e) {
      note('Save failed: ' + (e.message || e), false);
    }
  }

  async function list() {
    const c = client(); const w = wizard();
    if (!c || !w) return [];
    const res = await c.from('filings').select('*')
      .eq('form_type', w.formType).order('updated_at', { ascending: false });
    if (res.error) { note('Could not load filings: ' + res.error.message, false); return []; }
    return res.data || [];
  }

  async function load(id) {
    const c = client(); const w = wizard();
    if (!c || !w) return;
    const res = await c.from('filings').select('*').eq('id', id).single();
    if (res.error) { note('Load failed: ' + res.error.message, false); return; }
    ST.currentId = res.data.id;
    try { w.restore(res.data.data || {}); note('Filing loaded.', true); }
    catch (e) { note('Could not restore: ' + (e.message || e), false); }
    closePanel();
  }

  async function remove(id, ev) {
    if (ev) ev.stopPropagation();
    const c = client(); if (!c) return;
    const res = await c.from('filings').delete().eq('id', id);
    if (res.error) { note('Delete failed: ' + res.error.message, false); return; }
    if (ST.currentId === id) ST.currentId = null;
    openPanel();   // re-render the list
  }

  function bar() { return document.getElementById('saves-bar'); }
  function panel() { return document.getElementById('saves-panel'); }

  function closePanel() { const p = panel(); if (p) p.classList.add('hidden'); }

  async function openPanel() {
    const p = panel(); if (!p) return;
    p.innerHTML = '<div class="saves-loading">Loading…</div>';
    p.classList.remove('hidden');
    const rows = await list();
    if (!rows.length) { p.innerHTML = '<div class="saves-empty">No saved filings yet.</div>'; return; }
    p.innerHTML = rows.map(r => {
      const when = new Date(r.updated_at).toLocaleString();
      return `<div class="saves-row" data-id="${r.id}">
        <div class="saves-meta"><strong>${esc(r.title || r.api_number || 'Filing')}</strong>
          <span class="saves-when">${esc(when)}</span></div>
        <button class="saves-del" data-del="${r.id}" title="Delete">✕</button>
      </div>`;
    }).join('');
    p.querySelectorAll('.saves-row').forEach(el =>
      el.onclick = () => load(el.dataset.id));
    p.querySelectorAll('.saves-del').forEach(el =>
      el.onclick = (e) => remove(el.dataset.del, e));
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function refresh() {
    const b = bar();
    if (!b) return;
    if (!signedIn() || !wizard()) { b.classList.add('hidden'); closePanel(); return; }
    b.innerHTML = `<button class="auth-btn" id="saves-save">💾 Save</button>`
      + `<button class="auth-btn" id="saves-open">📂 Resume</button>`;
    b.querySelector('#saves-save').onclick = save;
    b.querySelector('#saves-open').onclick = () => {
      const p = panel();
      if (p && !p.classList.contains('hidden')) closePanel(); else openPanel();
    };
    b.classList.remove('hidden');
  }

  window.PlugfileSaves = { refresh, save, openPanel };
  // auth.js calls refresh() on auth-state changes; also try once on load.
  document.addEventListener('DOMContentLoaded', refresh);
})();
