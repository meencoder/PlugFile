'use strict';

// ===========================================================================
// Plugfile — W-3A "Notice of Intent to Plug" wizard
// A second PWA flow (pre-plugging). Reuses the same API as the W-3 wizard.
// ===========================================================================

const S = {
  step: 1,
  apiNumber: '',
  wellData: null,
  buqwDepth: null,
  gauRef: null,
  aorFindings: [],
  aorGuidanceLoaded: false,
  wellType: 'oil',
  completionType: 'single',
  cementingCompany: null,
  sharedWith: null,        // plugging-company email this filing was shared with
  plugsComputed: false,
  attach: { gau: false, w15: false, l1: false, p13: false },
  sigName: '',
  sigTitle: 'Operator Representative',
  certDate: '',
  pdfUrl: null,
  pdfFilename: '',
  maxStep: 1,
};

// ---- DOM helpers ----------------------------------------------------------
const el   = id => document.getElementById(id);
const show = e  => e.classList.remove('hidden');
const hide = e  => e.classList.add('hidden');
const esc  = s  => String(s == null ? '' : s).replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function toast(msg, type = 'error') {
  const t = document.createElement('div');
  t.textContent = msg;
  t.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
    background:${type === 'error' ? '#ef4444' : '#22c55e'};color:#fff;padding:12px 20px;
    border-radius:10px;font-size:0.88rem;font-weight:600;z-index:999;max-width:90vw;
    text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.4);`;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

async function apiJson(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ---- Step navigation ------------------------------------------------------
const STEP_NAMES = ['Well', 'GAU', 'AOR', 'Plugs', 'Docs', 'Sign', 'File'];

function goTo(n) {
  document.querySelectorAll('.step').forEach(s =>
    s.classList.toggle('active', +s.dataset.step === n));
  S.step = n;
  S.maxStep = Math.max(S.maxStep || 1, n);
  document.querySelectorAll('.step-pip').forEach((pip, i) => {
    const s = i + 1;
    pip.classList.toggle('done', s < n);
    pip.classList.toggle('active', s === n);
    pip.classList.toggle('nav', s <= S.maxStep && s !== n);
    pip.title = (STEP_NAMES[i] || ('Step ' + s)) + (s <= S.maxStep ? '' : ' (locked)');
  });
  el('step-name').textContent = STEP_NAMES[n - 1];
  window.scrollTo({ top: 0, behavior: 'smooth' });

  if (n === 3) ensureAor();
  if (n === 4 && !S.plugsComputed) computePlugs();
  if (n === 5) renderAttachments();
  if (n === 6 && !el('cert-date').value) {
    el('cert-date').value = new Date().toISOString().slice(0, 10);
  }
}

// ---- overrides builder ----------------------------------------------------
function buildOverrides() {
  const ov = { well_type: S.wellType, completion_type: S.completionType };
  // Box 22 (cementing/plugging company): an explicit entry wins; otherwise
  // fall back to the plugging company this filing was shared with.
  const cementer = S.cementingCompany || S.sharedWith;
  if (cementer) ov.cementing_company = cementer;
  if (S.sigName)  ov.operator_signature_name = S.sigName;
  if (S.sigTitle) ov.operator_title = S.sigTitle;
  if (S.certDate) ov.certification_date = S.certDate;
  if (S.aorFindings.length) ov.aor_findings = S.aorFindings;
  return ov;
}

// ===========================================================================
// Step 1 — Well lookup
// ===========================================================================
el('btn-lookup').addEventListener('click', async () => {
  const api = el('api-number').value.trim().replace(/[^0-9\-]/g, '');
  if (!api) { toast('Enter an API number first.'); return; }
  const btn = el('btn-lookup');
  btn.disabled = true; btn.textContent = 'Looking up…';
  try {
    const data = await apiJson('/api/lookup', { api_number: api });
    S.apiNumber = api;
    S.wellData = data;
    el('well-result').innerHTML = `
      <div class="result-row"><span class="rlabel">Lease / Well</span>
        <span>${esc(data.lease_name || '—')} #${esc(data.well_number || '—')}</span></div>
      <div class="result-row"><span class="rlabel">County</span><span>${esc(data.county || '—')}</span></div>
      <div class="result-row"><span class="rlabel">District</span><span>${esc(data.rrc_district || '—')}</span></div>
      <div class="result-row"><span class="rlabel">Field</span><span>${esc(data.field_name || '—')}</span></div>`;
    show(el('well-result'));
    hide(el('btn-lookup')); hide(el('btn-skip-lookup')); show(el('btn-well-continue'));
  } catch (e) {
    toast(`Lookup failed: ${e.message}. Continue manually.`);
    S.apiNumber = api;
  } finally {
    btn.disabled = false; btn.textContent = 'Look up well →';
  }
});

el('btn-skip-lookup').addEventListener('click', () => {
  S.apiNumber = el('api-number').value.trim() || '42-000-00000';
  goTo(2);
});
el('btn-well-continue').addEventListener('click', () => goTo(2));

// ===========================================================================
// Step 2 — GAU letter
// ===========================================================================
el('gau-file').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;
  const lbl = el('gau-upload-label');
  lbl.textContent = `Processing ${file.name}…`;
  const form = new FormData();
  form.append('file', file);
  if (S.apiNumber) form.append('api_number', S.apiNumber);
  try {
    const res = await fetch('/api/gau', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    S.buqwDepth = data.buqw_depth_ft;
    S.gauRef = data.gau_letter_reference;
    const specials = data.special_requirements.length
      ? `<div class="result-row sp"><span class="rlabel">⚠ Special</span><span>${esc(data.special_requirements.join('; '))}</span></div>` : '';
    el('gau-result').innerHTML = `
      <div class="result-row"><span class="rlabel">BUQW Depth</span><span class="hi">${data.buqw_depth_ft.toLocaleString()} ft</span></div>
      <div class="result-row"><span class="rlabel">Reference</span><span>${esc(data.gau_letter_reference)}</span></div>
      <div class="result-row"><span class="rlabel">Type</span><span>${esc(data.letter_type)}</span></div>
      ${specials}`;
    show(el('gau-result'));
    renderGauVerdict(data.acceptability);
    S.attach.gau = true;   // a parsed letter counts as the GAU attachment
    lbl.textContent = file.name + ' ✓';
  } catch (err) {
    toast(`Could not parse GAU letter: ${err.message}`);
    lbl.textContent = 'Tap to upload GAU letter PDF';
    hide(el('gau-verdict'));
  }
});

function renderGauVerdict(v) {
  const box = el('gau-verdict');
  if (!v) { hide(box); return; }
  const ok = v.acceptable_for_plugging;
  box.className = 'verdict ' + (ok ? (v.confidence === 'low' ? 'warn' : 'pass') : 'fail');
  const headline = ok
    ? (v.confidence === 'low' ? '⚠ Likely OK — verify it is the plugging determination' : '✓ Acceptable for plugging')
    : '✕ This letter looks wrong for plugging';
  const blocking = (v.blocking_issues || []).length
    ? `<ul class="verdict-list fail">${v.blocking_issues.map(b => `<li>${esc(b)}</li>`).join('')}</ul>` : '';
  const warns = (v.warnings || []).length
    ? `<ul class="verdict-list warn">${v.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : '';
  box.innerHTML = `<div class="verdict-head">${headline}
    <span class="verdict-conf">${esc(v.confidence)} confidence</span></div>${blocking}${warns}`;
  show(box);
}

el('btn-step2-next').addEventListener('click', () => goTo(3));
el('btn-step2-skip').addEventListener('click', () => goTo(3));

// ===========================================================================
// Step 3 — Area of Review
// ===========================================================================
async function ensureAor() { if (!S.aorGuidanceLoaded) loadAor(); }

// Fast path: import the GIS Viewer "Download Wells" export.
el('aor-file').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;
  const api = S.apiNumber || el('api-number').value.trim();
  if (!api || api === '42-000-00000') { toast('Look up a real well first.'); return; }
  const lbl = el('aor-upload-label');
  lbl.textContent = `Importing ${file.name}…`;
  const form = new FormData();
  form.append('file', file);
  form.append('api_number', api);
  try {
    const res = await fetch('/api/aor/import', { method: 'POST', body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const d = await res.json();
    S.aorFindings = (d.import && d.import.findings) || [];
    S.aorGuidanceLoaded = true;
    S.plugsComputed = false;   // findings changed → recompute the plug program
    const s = d.import.summary;
    const box = el('aor-import-summary');
    box.innerHTML = `Imported ${s.total_rows} well(s): <strong>${s.of_concern}</strong> of concern · `
      + `${s.plugged_skipped} plugged (skipped) · ${s.out_of_radius} outside ${s.radius_mi} mi`
      + (s.distances_computed ? '' : ' · distances not computed (no subject coordinates)');
    show(box);
    renderAorGuidance(d.review_guidance || []);
    renderAorResults(d);
    lbl.textContent = file.name + ' ✓';
  } catch (err) {
    toast(`Import failed: ${err.message}`);
    lbl.textContent = 'Import "Download Wells" export (.csv / .xlsx)';
  }
});

el('btn-aor-add').addEventListener('click', () => {
  const wellId = el('aor-well-id').value.trim();
  const zone = el('aor-zone').value.trim();
  const depth = el('aor-depth').value;
  const distance = el('aor-distance').value;
  if (!wellId && !zone) { toast('Enter at least a well ID or zone.'); return; }
  S.aorFindings.push({
    well_id: wellId || null, zone_name: zone || null,
    depth_ft: depth !== '' ? parseFloat(depth) : null,
    distance_mi: distance !== '' ? parseFloat(distance) : null,
  });
  el('aor-well-id').value = ''; el('aor-zone').value = '';
  el('aor-depth').value = ''; el('aor-distance').value = '';
  S.plugsComputed = false;   // findings changed → plug program must recompute
  loadAor();
});

async function loadAor() {
  const api = S.apiNumber || el('api-number').value.trim();
  if (!api) { toast('Look up a well first.'); return; }
  try {
    const a = await apiJson('/api/aor', {
      api_number: api,
      overrides: S.aorFindings.length ? { aor_findings: S.aorFindings } : null,
    });
    S.aorGuidanceLoaded = true;
    renderAorGuidance(a.review_guidance || []);
    renderAorResults(a);
  } catch (e) { toast(`AOR check failed: ${e.message}`); }
}

function renderAorGuidance(steps) {
  if (!steps.length) return;
  el('aor-guidance').innerHTML = `<h3>RRC GIS-Viewer review steps</h3><ul>` +
    steps.map(s => `<li><strong>${s.order}. ${esc(s.title)}</strong><br>
      <span class="muted-inline">${esc(s.detail)}</span></li>`).join('') + `</ul>`;
}

function renderAorResults(a) {
  const box = el('aor-results');
  if (!a.findings || !a.findings.length) { hide(box); return; }
  const summary = `<div class="aor-summary">${a.finding_count} finding(s) ·
    ${a.in_aor_count} within ${a.radius_mi} mi · ${a.isolation_required_count} need isolation${
    a.total_isolation_sacks ? ` · ~${a.total_isolation_sacks} sx total` : ''}</div>`;
  const rows = a.findings.map(f => {
    const cls = f.requires_isolation ? 'iso' : (f.in_aor ? 'inradius' : 'outside');
    const tag = f.requires_isolation ? '⚠ isolation plug' : (f.in_aor ? 'in radius' : 'outside ½ mi');
    const plug = f.requires_isolation
      ? `<div class="aor-plug">Plug ${Math.round(f.isolation_top_ft)}–${Math.round(f.isolation_bottom_ft)} ft
         · ~${f.isolation_volume_sacks} sx · ${esc(f.cite || '')}</div>` : '';
    return `<div class="aor-finding ${cls}"><div class="aor-finding-head">
      <span>${esc(f.well_id || f.zone_name || 'finding')}</span><span class="aor-tag">${tag}</span></div>
      <div class="aor-note">${esc(f.note)}</div>${plug}</div>`;
  }).join('');
  box.innerHTML = summary + rows;
  show(box);
}

el('btn-step3-next').addEventListener('click', () => goTo(4));

// ===========================================================================
// Step 4 — Proposed plug program
// ===========================================================================
el('well-type').addEventListener('change', e => { S.wellType = e.target.value; S.plugsComputed = false; });
el('completion-type').addEventListener('change', e => { S.completionType = e.target.value; S.plugsComputed = false; });
el('btn-compute-plugs').addEventListener('click', computePlugs);

async function computePlugs() {
  const api = S.apiNumber;
  if (!api || api === '42-000-00000') {
    el('plug-list').innerHTML = `<p class="hint">Look up a real well to compute its plug program.</p>`;
    return;
  }
  const btn = el('btn-compute-plugs');
  btn.disabled = true; btn.textContent = 'Computing…';
  try {
    const p = await apiJson('/api/plug-program', { api_number: api, overrides: buildOverrides() });
    S.plugsComputed = true;
    el('plug-summary').innerHTML = `${p.plug_count} plug(s) · TD ${p.total_depth_ft?.toLocaleString()} ft ·
      BUQW ${p.buqw_depth_ft?.toLocaleString()} ft${
      p.total_cement_sacks ? ` · ~${p.total_cement_sacks} sx cement` : ''}`;
    show(el('plug-summary'));
    el('plug-list').innerHTML = (p.plugs || []).map(pl => `
      <div class="plug-item">
        <div class="plug-head"><span>#${pl.rank} · ${esc(pl.kind)}</span>
          <span class="plug-depth">${Math.round(pl.top_ft)}–${Math.round(pl.bottom_ft)} ft</span></div>
        <div class="aor-note">${esc(pl.rationale)}</div>
        <div class="plug-meta">${pl.volume_sacks ? `~${pl.volume_sacks} sx · ` : ''}${esc(pl.cite)}</div>
      </div>`).join('');
  } catch (e) {
    toast(`Plug computation failed: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = 'Recompute plug program';
  }
}

el('btn-step4-next').addEventListener('click', () => goTo(5));

// ===========================================================================
// Step 5 — Required attachments
// ===========================================================================
const ATTACH_KEYS = [
  ['gau', 'has_gau_letter'],
  ['w15', 'has_w15_plugging_permit'],
  ['l1',  'has_l1_well_log'],
  ['p13', 'has_p13_affidavit'],
];

async function renderAttachments() {
  const api = S.apiNumber || '42-000-00000';
  let data;
  try {
    data = await apiJson('/api/attachments/check', {
      api_number: api, form_type: 'w3a',
      has_gau_letter: S.attach.gau, has_w15_plugging_permit: S.attach.w15,
      has_l1_well_log: S.attach.l1, has_p13_affidavit: S.attach.p13,
      gau_reference: S.gauRef,
    });
  } catch (e) { toast(`Attachments check failed: ${e.message}`); return; }

  const keyMap = { gau_letter: 'gau', w15_plugging_permit: 'w15', l1_well_log: 'l1', p13_affidavit: 'p13' };
  el('attach-list').innerHTML = data.items.map(it => {
    const sk = keyMap[it.key];
    return `<div class="attach-item ${it.present ? 'on' : (it.required ? 'req' : 'opt')}" data-key="${sk}">
      <div class="attach-head">
        <span class="attach-check">${it.present ? '☑' : '☐'}</span>
        <span class="attach-name">${esc(it.display_name)}${it.required ? '' : ' <span class="muted-inline">(not required)</span>'}</span>
      </div>
      <div class="aor-note">${esc(it.tip)}</div>
    </div>`;
  }).join('');

  document.querySelectorAll('.attach-item').forEach(item => {
    item.addEventListener('click', () => {
      const k = item.dataset.key;
      S.attach[k] = !S.attach[k];
      renderAttachments();
    });
  });

  const sum = el('attach-summary');
  sum.className = 'aor-summary' + (data.ready ? ' ready-ok' : '');
  sum.innerHTML = data.ready
    ? `✓ All ${data.required_count} required attachments ready.`
    : `${data.present_count}/${data.required_count} ready · still need: ${data.missing.join(', ')}`;
  show(sum);
}

el('btn-step5-next').addEventListener('click', () => goTo(6));

// ===========================================================================
// Step 6 — Sign & generate
// ===========================================================================
// Build the W-3A PDF from current state and wire the download link to it.
// Returns true on success. Shared by the Step-6 "Generate" button and the
// Step-7 download link (which regenerates on demand — see below).
async function generatePdf() {
  S.cementingCompany = el('cementing-company').value.trim() || null;
  S.sigName  = el('sig-name').value.trim();
  S.sigTitle = el('sig-title').value.trim() || 'Operator Representative';
  S.certDate = el('cert-date').value;
  if (!S.sigName)  { toast('Enter the certifying official\'s name.'); return false; }
  if (!S.certDate) { toast('Enter the certification date.'); return false; }

  hide(el('missing-box'));
  // Surface any still-missing required fields (advisory).
  const pf = await apiJson('/api/w3a/prefill', { api_number: S.apiNumber, overrides: buildOverrides() });
  if (pf.missing_required && pf.missing_required.length) {
    el('missing-box').innerHTML = pf.missing_required
      .map(m => `<div class="warn-item">⚠ Still missing: ${esc(m)}</div>`).join('');
    show(el('missing-box'));
  }

  const authH = (window.PlugfileAuth && window.PlugfileAuth.authHeaders()) || {};
  const res = await fetch('/api/w3a/generate', {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...authH },
    body: JSON.stringify({ api_number: S.apiNumber, overrides: buildOverrides(), paid_tier: false }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  const blob = await res.blob();
  if (S.pdfUrl) URL.revokeObjectURL(S.pdfUrl);
  S.pdfUrl = URL.createObjectURL(blob);
  S.pdfFilename = `W3A_${(S.apiNumber || '').replace(/-/g, '')}_DRAFT.pdf`;
  el('download-link').href = S.pdfUrl;
  el('download-link').download = S.pdfFilename;
  return true;
}

el('btn-generate').addEventListener('click', async () => {
  const btn = el('btn-generate');
  btn.disabled = true; btn.textContent = 'Generating…';
  try {
    if (await generatePdf()) { loadPackage(); goTo(7); }
  } catch (e) {
    toast(`W-3A generation failed: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = 'Generate W-3A →';
  }
});

// Resuming a saved filing jumps straight to the package step (Step 7) without
// generating a PDF, so the link's href is still "#". Without this guard a
// click would download the page's own HTML. Generate on demand first, then
// let the (now real) blob download proceed.
el('download-link').addEventListener('click', async (e) => {
  if (S.pdfUrl) return;                 // real PDF already in memory — download it
  if (!S.apiNumber) return;             // nothing to generate from
  e.preventDefault();
  const a = el('download-link');
  const label = a.textContent;
  a.textContent = 'Generating…';
  try {
    if (await generatePdf()) a.click(); // re-fire now that href is a blob URL
  } catch (err) {
    toast(`W-3A generation failed: ${err.message}`);
  } finally {
    a.textContent = label;
  }
});

// ===========================================================================
// Step 7 — Filing package (district office + handoff + portal strings)
// ===========================================================================
function loadPackage() {
  loadDistrictOffice();
  loadHandoff();
  loadPortal();
}

async function loadDistrictOffice() {
  const box = el('district-office');
  if (!S.apiNumber || S.apiNumber === '42-000-00000') { hide(box); return; }
  try {
    const r = await apiJson('/api/district-office', { api_number: S.apiNumber });
    if (!r.matched || !r.office) { hide(box); return; }
    const o = r.office;
    const fax = o.fax ? `<div class="result-row"><span class="rlabel">Fax</span><span>${esc(o.fax)}</span></div>` : '';
    box.innerHTML = `
      <div class="result-row"><span class="rlabel">File with</span><span class="hi">${esc(o.name)} District Office</span></div>
      <div class="result-row"><span class="rlabel">Address</span><span>${esc(o.address_line1)}, ${esc(o.city_state_zip)}</span></div>
      <div class="result-row"><span class="rlabel">Phone</span><span>${esc(o.phone)}</span></div>
      ${fax}
      <div class="result-row"><span class="rlabel">Email</span><span>${esc(o.email)}</span></div>`;
    show(box);
  } catch (e) { hide(box); }
}

async function loadHandoff() {
  const box = el('handoff-box');
  if (!S.apiNumber || S.apiNumber === '42-000-00000') { hide(box); return; }
  try {
    // If the filing has been shared with a plugging company, it has left the
    // operator's desk — the live stage is "Plugging company review", and the
    // named plugging company rides along so the workflow can label the holder.
    const shared = !!S.sharedWith;
    const h = await apiJson('/api/handoff', {
      api_number: S.apiNumber,
      stage: shared ? 'plugging_company_review' : 'operator_review',
      form_type: 'w3a',
      plugging_company: S.sharedWith || null,
      has_gau_letter: S.attach.gau, has_w15_plugging_permit: S.attach.w15,
      has_l1_well_log: S.attach.l1, has_p13_affidavit: S.attach.p13,
      has_plugging_details: true, operator_certified: !shared,
    });
    const status = h.can_advance
      ? `<div class="result-row"><span class="rlabel">Next</span><span class="hi">${esc(h.next_action)} → ${esc(h.next_holder_label)}</span></div>`
      : `<ul class="verdict-list warn">${(h.blocking || []).map(b => `<li>${esc(b)}</li>`).join('')}</ul>`;
    const steps = h.workflow.map(w => {
      const here = w.stage === h.current_stage;
      return `<div class="hand-step ${here ? 'here' : ''}">${here ? '▶ ' : ''}${esc(w.holder_label)} — ${esc(w.title)}</div>`;
    }).join('');
    box.innerHTML = `
      <div class="result-row"><span class="rlabel">Holder</span><span>${esc(h.holder_label)} (${esc(h.title)})</span></div>
      ${status}
      <div class="hand-flow">${steps}</div>`;
    show(box);
  } catch (e) { hide(box); }
}

async function loadPortal() {
  const box = el('portal-box');
  if (!S.apiNumber || S.apiNumber === '42-000-00000') { hide(box); return; }
  try {
    const p = await apiJson('/api/portal-format', { api_number: S.apiNumber, overrides: buildOverrides() });
    const d = p.depths || {}, wi = p.well_identity || {};
    const casing = (p.casing || []).map(c =>
      `<div class="result-row"><span class="rlabel">Casing OD</span><span>${esc(c.od_in)}" @ ${esc(c.set_depth_ft)} ft</span></div>`).join('');
    box.innerHTML = `
      <div class="result-row"><span class="rlabel">Operator</span><span>${esc(wi.operator_name || '—')}</span></div>
      <div class="result-row"><span class="rlabel">District</span><span>${esc(wi.rrc_district || '—')}</span></div>
      <div class="result-row"><span class="rlabel">Total depth</span><span>${esc(d.total_depth_ft || '—')}</span></div>
      <div class="result-row"><span class="rlabel">BUQW depth</span><span>${esc(d.buqw_depth_ft || '—')}</span></div>
      ${casing}
      <div class="aor-note" style="margin-top:8px">Sizes are pre-formatted to the RRC portal's exact format (fractions, integers).</div>`;
    show(box);
  } catch (e) { hide(box); }
}

// ===========================================================================
// Restart
// ===========================================================================
el('btn-restart').addEventListener('click', () => {
  if (S.pdfUrl) URL.revokeObjectURL(S.pdfUrl);
  Object.assign(S, {
    step: 1, apiNumber: '', wellData: null, buqwDepth: null, gauRef: null,
    aorFindings: [], aorGuidanceLoaded: false, wellType: 'oil',
    completionType: 'single', cementingCompany: null, sharedWith: null,
    plugsComputed: false,
    attach: { gau: false, w15: false, l1: false, p13: false },
    sigName: '', sigTitle: 'Operator Representative', certDate: '', pdfUrl: null,
    maxStep: 1,
  });
  ['api-number', 'aor-well-id', 'aor-zone', 'aor-depth', 'aor-distance',
   'cementing-company', 'sig-name', 'cert-date'].forEach(id => { if (el(id)) el(id).value = ''; });
  el('gau-upload-label').textContent = 'Tap to upload GAU letter PDF';
  ['well-result', 'gau-result', 'gau-verdict', 'aor-results', 'aor-import-summary',
   'plug-summary', 'attach-summary', 'missing-box', 'district-office', 'handoff-box', 'portal-box']
    .forEach(id => hide(el(id)));
  if (el('aor-upload-label')) el('aor-upload-label').textContent = 'Import "Download Wells" export (.csv / .xlsx)';
  ['aor-guidance', 'plug-list', 'attach-list'].forEach(id => { el(id).innerHTML = ''; });
  show(el('btn-lookup')); show(el('btn-skip-lookup')); hide(el('btn-well-continue'));
  goTo(1);
});

// ---- Save / resume hooks (used by saves.js when signed in) ----------------
window.toast = toast;
window.PlugfileWizard = {
  formType: 'w3a',
  title: () => `W-3A ${S.apiNumber || 'draft'}`,
  // saves.js calls this with the filing's shared_with_email on load/share so
  // the handoff stage + Box 22 reflect the plugging company.
  setSharedWith: (email) => {
    S.sharedWith = (email || '').trim().toLowerCase() || null;
    if (S.step === 7) loadPackage();   // refresh the handoff card if on it
  },
  getState: () => ({
    api: S.apiNumber, step: S.step,
    buqwDepth: S.buqwDepth, gauRef: S.gauRef,
    aorFindings: S.aorFindings,
    wellType: S.wellType, completionType: S.completionType,
    cementingCompany: el('cementing-company') ? el('cementing-company').value : S.cementingCompany,
    attach: S.attach,
    sigName: el('sig-name') ? el('sig-name').value : '',
    sigTitle: el('sig-title') ? el('sig-title').value : '',
    certDate: el('cert-date') ? el('cert-date').value : '',
  }),
  restore: (d) => {
    S.apiNumber = d.api || '';
    S.buqwDepth = d.buqwDepth ?? null;
    S.gauRef = d.gauRef ?? null;
    S.aorFindings = d.aorFindings || [];
    S.aorGuidanceLoaded = false;
    S.wellType = d.wellType || 'oil';
    S.completionType = d.completionType || 'single';
    S.cementingCompany = d.cementingCompany || null;
    S.attach = d.attach || { gau: false, w15: false, l1: false, p13: false };
    S.plugsComputed = false;
    if (el('api-number')) el('api-number').value = d.api || '';
    if (el('well-type')) el('well-type').value = S.wellType;
    if (el('completion-type')) el('completion-type').value = S.completionType;
    if (el('cementing-company')) el('cementing-company').value = d.cementingCompany || '';
    if (el('sig-name')) el('sig-name').value = d.sigName || '';
    if (el('sig-title')) el('sig-title').value = d.sigTitle || 'Operator Representative';
    if (el('cert-date')) el('cert-date').value = d.certDate || '';
    goTo(d.step >= 1 && d.step <= 7 ? d.step : 1);
  },
};

// ---- Boot -----------------------------------------------------------------
// Clickable step breadcrumb: jump back to any step already reached.
document.querySelectorAll('.step-pip').forEach((pip, i) => {
  pip.addEventListener('click', () => { if (i + 1 <= (S.maxStep || 1)) goTo(i + 1); });
});
goTo(1);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(console.warn);
}
