'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const S = {
  step: 1,
  apiNumber: '',
  wellData: null,
  buqwDepth: null,
  gauRef: null,
  transcript: '',
  narrative: '',
  slots: {},
  warnings: [],
  pdfUrl: null,
  pdfFilename: '',
  aorFindings: [],
  aorGuidanceLoaded: false,
};

const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const el   = id => document.getElementById(id);
const show = e  => e.classList.remove('hidden');
const hide = e  => e.classList.add('hidden');

function toast(msg, type = 'error') {
  const t = document.createElement('div');
  t.textContent = msg;
  t.style.cssText = `
    position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
    background:${type === 'error' ? '#ef4444' : '#22c55e'};
    color:#fff; padding:12px 20px; border-radius:10px;
    font-size:0.88rem; font-weight:600; z-index:999;
    max-width:90vw; text-align:center; box-shadow:0 4px 20px rgba(0,0,0,0.4);
  `;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

async function apiFetch(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res;
}

// ---------------------------------------------------------------------------
// Step navigation
// ---------------------------------------------------------------------------
const STEP_NAMES = ['Well', 'GAU', 'Voice', 'Review', 'PDF'];

function goTo(n) {
  document.querySelectorAll('.step').forEach(s => {
    s.classList.toggle('active', +s.dataset.step === n);
  });
  S.step = n;
  // Update step pips
  document.querySelectorAll('.step-pip').forEach((pip, i) => {
    const s = i + 1;
    pip.classList.toggle('done',   s < n);
    pip.classList.toggle('active', s === n);
    pip.classList.toggle('future', s > n);
  });
  el('step-name').textContent = STEP_NAMES[n - 1];
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ---------------------------------------------------------------------------
// Speech recognition
// ---------------------------------------------------------------------------
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isRecording = false;
let finalText = '';

if (SR) {
  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  recognition.onresult = e => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t + ' ';
      else interim += t;
    }
    el('transcript').value = finalText + interim;
  };

  recognition.onerror = e => {
    setRecording(false);
    if (e.error === 'not-allowed') toast('Microphone access denied — please type your transcript below.');
  };

  // Auto-restart while isRecording (avoids 60-second Safari timeout)
  recognition.onend = () => { if (isRecording) recognition.start(); };
} else {
  el('btn-record').disabled = true;
  el('btn-record').querySelector('.mic-lbl').textContent = 'Type transcript below';
}

function setRecording(on) {
  isRecording = on;
  el('btn-record').classList.toggle('recording', on);
  el('btn-record').querySelector('.mic-lbl').textContent = on ? 'Tap to stop' : 'Tap to record';
  el('rec-indicator').classList.toggle('hidden', !on);
}

// ---------------------------------------------------------------------------
// Step 1 — Well lookup
// ---------------------------------------------------------------------------
el('btn-lookup').addEventListener('click', async () => {
  const api = el('api-number').value.trim().replace(/[^0-9\-]/g, '');
  if (!api) { toast('Enter an API number first.'); return; }

  const btn = el('btn-lookup');
  btn.disabled = true;
  btn.textContent = 'Looking up…';

  try {
    const res = await apiFetch('/api/lookup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_number: api }),
    });
    const data = await res.json();
    S.apiNumber = api;
    S.wellData  = data;

    el('well-result').innerHTML = `
      <div class="result-row">
        <span class="rlabel">Operator</span>
        <span>${data.operator_name || '—'}</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Lease / Well</span>
        <span>${data.lease_name || '—'} #${data.well_number || '—'}</span>
      </div>
      <div class="result-row">
        <span class="rlabel">County</span>
        <span>${data.county || '—'}</span>
      </div>
      <div class="result-row">
        <span class="rlabel">District</span>
        <span>${data.rrc_district || '—'}</span>
      </div>`;
    show(el('well-result'));

    // Reveal the optional AOR helper + an explicit continue button instead of
    // auto-advancing, so the operator can run the area-of-review check first.
    show(el('aor-panel'));
    hide(el('btn-lookup'));
    hide(el('btn-skip-lookup'));
    show(el('btn-well-continue'));
  } catch (e) {
    toast(`Lookup failed: ${e.message}. Continue manually.`);
    S.apiNumber = api;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Look up well →';
  }
});

el('btn-skip-lookup').addEventListener('click', () => {
  S.apiNumber = el('api-number').value.trim() || '42-000-00000';
  goTo(2);
});

el('btn-well-continue').addEventListener('click', () => goTo(2));

// ---------------------------------------------------------------------------
// Step 1 — Area-of-Review helper (optional)
// ---------------------------------------------------------------------------
el('btn-aor-toggle').addEventListener('click', () => {
  const body = el('aor-body');
  body.classList.toggle('hidden');
  if (!body.classList.contains('hidden') && !S.aorGuidanceLoaded) {
    loadAor();   // first open → fetch the GIS-Viewer checklist
  }
});

el('btn-aor-add').addEventListener('click', () => {
  const wellId   = el('aor-well-id').value.trim();
  const zone     = el('aor-zone').value.trim();
  const depth    = el('aor-depth').value;
  const distance = el('aor-distance').value;

  if (!wellId && !zone) { toast('Enter at least a well ID or zone.'); return; }

  S.aorFindings.push({
    well_id:     wellId || null,
    zone_name:   zone || null,
    depth_ft:    depth    !== '' ? parseFloat(depth)    : null,
    distance_mi: distance !== '' ? parseFloat(distance) : null,
  });

  // Clear inputs for the next entry.
  el('aor-well-id').value = '';
  el('aor-zone').value    = '';
  el('aor-depth').value   = '';
  el('aor-distance').value = '';

  loadAor();
});

async function loadAor() {
  const api = S.apiNumber || el('api-number').value.trim();
  if (!api) { toast('Look up a well first.'); return; }

  try {
    const res = await apiFetch('/api/aor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_number: api,
        overrides: S.aorFindings.length ? { aor_findings: S.aorFindings } : null,
      }),
    });
    const a = await res.json();
    S.aorGuidanceLoaded = true;
    renderAorGuidance(a.review_guidance || []);
    renderAorResults(a);
  } catch (e) {
    toast(`AOR check failed: ${e.message}`);
  }
}

function renderAorGuidance(steps) {
  if (!steps.length) return;
  el('aor-guidance').innerHTML =
    `<h3>RRC GIS-Viewer review steps</h3><ul>` +
    steps.map(s => `<li><strong>${s.order}. ${esc(s.title)}</strong><br>
      <span class="muted-inline">${esc(s.detail)}</span></li>`).join('') +
    `</ul>`;
}

function renderAorResults(a) {
  const box = el('aor-results');
  if (!a.findings || !a.findings.length) {
    hide(box);
    return;
  }
  const summary = `<div class="aor-summary">
    ${a.finding_count} finding(s) · ${a.in_aor_count} within ${a.radius_mi} mi ·
    ${a.isolation_required_count} need isolation${
      a.total_isolation_sacks ? ` · ~${a.total_isolation_sacks} sx total` : ''}
  </div>`;

  const rows = a.findings.map(f => {
    const cls = f.requires_isolation ? 'iso' : (f.in_aor ? 'inradius' : 'outside');
    const tag = f.requires_isolation ? '⚠ isolation plug'
              : (f.in_aor ? 'in radius' : 'outside ½ mi');
    const plug = f.requires_isolation
      ? `<div class="aor-plug">Plug ${Math.round(f.isolation_top_ft)}–${Math.round(f.isolation_bottom_ft)} ft
         · ~${f.isolation_volume_sacks} sx · ${esc(f.cite || '')}</div>`
      : '';
    return `<div class="aor-finding ${cls}">
      <div class="aor-finding-head">
        <span>${esc(f.well_id || f.zone_name || 'finding')}</span>
        <span class="aor-tag">${tag}</span>
      </div>
      <div class="aor-note">${esc(f.note)}</div>
      ${plug}
    </div>`;
  }).join('');

  box.innerHTML = summary + rows;
  show(box);
}

// ---------------------------------------------------------------------------
// Step 2 — GAU letter
// ---------------------------------------------------------------------------
el('gau-file').addEventListener('change', async e => {
  const file = e.target.files[0];
  if (!file) return;

  const lbl = el('gau-upload-label');
  lbl.textContent = `Processing ${file.name}…`;

  const form = new FormData();
  form.append('file', file);
  // Pass the well's API so the GW-2/H-15 check can catch a wrong-well letter.
  if (S.apiNumber) form.append('api_number', S.apiNumber);

  try {
    const res = await apiFetch('/api/gau', { method: 'POST', body: form });
    const data = await res.json();
    S.buqwDepth = data.buqw_depth_ft;
    S.gauRef    = data.gau_letter_reference;

    const specials = data.special_requirements.length
      ? `<div class="result-row sp"><span class="rlabel">⚠ Special</span><span>${esc(data.special_requirements.join('; '))}</span></div>`
      : '';

    el('gau-result').innerHTML = `
      <div class="result-row">
        <span class="rlabel">BUQW Depth</span>
        <span class="hi">${data.buqw_depth_ft.toLocaleString()} ft</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Reference</span>
        <span>${esc(data.gau_letter_reference)}</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Type</span>
        <span>${esc(data.letter_type)}</span>
      </div>
      ${specials}`;
    show(el('gau-result'));
    renderGauVerdict(data.acceptability);
    lbl.textContent = file.name + ' ✓';
    el('btn-step2-next').disabled = false;
  } catch (err) {
    toast(`Could not parse GAU letter: ${err.message}`);
    lbl.textContent = 'Tap to upload GAU letter PDF';
    hide(el('gau-verdict'));
    showManualBuqw();
  }
});

// GW-2 / H-15 "acceptable for plugging" verdict banner.
function renderGauVerdict(v) {
  const box = el('gau-verdict');
  if (!v) { hide(box); return; }

  const ok = v.acceptable_for_plugging;
  box.className = 'verdict ' + (ok ? (v.confidence === 'low' ? 'warn' : 'pass') : 'fail');

  const headline = ok
    ? (v.confidence === 'low'
        ? '⚠ Likely OK — verify it is the plugging determination'
        : '✓ Acceptable for plugging')
    : '✕ This letter looks wrong for plugging';

  const blocking = (v.blocking_issues || []).length
    ? `<ul class="verdict-list fail">${v.blocking_issues.map(b => `<li>${esc(b)}</li>`).join('')}</ul>`
    : '';
  const warns = (v.warnings || []).length
    ? `<ul class="verdict-list warn">${v.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul>`
    : '';

  box.innerHTML = `
    <div class="verdict-head">${headline}
      <span class="verdict-conf">${esc(v.confidence)} confidence</span>
    </div>
    ${blocking}${warns}`;
  show(box);
}

function showManualBuqw() {
  show(el('manual-buqw-group'));
  el('btn-step2-next').disabled = false;
}

el('btn-enter-buqw-manually').addEventListener('click', showManualBuqw);

el('btn-step2-next').addEventListener('click', () => {
  const manBuqw = el('manual-buqw').value;
  if (manBuqw) {
    S.buqwDepth = parseFloat(manBuqw);
    S.gauRef    = el('manual-gau-ref').value.trim() || null;
  }
  goTo(3);
});

el('btn-step2-skip').addEventListener('click', () => {
  S.buqwDepth = null;
  S.gauRef    = null;
  goTo(3);
});

// ---------------------------------------------------------------------------
// Step 3 — Voice recording
// ---------------------------------------------------------------------------
el('btn-record').addEventListener('click', () => {
  if (!recognition) return;
  if (isRecording) {
    recognition.stop();
    setRecording(false);
  } else {
    finalText = el('transcript').value;   // preserve typed text
    recognition.start();
    setRecording(true);
  }
});

el('btn-process').addEventListener('click', async () => {
  if (isRecording) { recognition.stop(); setRecording(false); }

  const transcript = el('transcript').value.trim();
  if (!transcript) { toast('Dictate or type your transcript first.'); return; }
  S.transcript = transcript;

  const btn = el('btn-process');
  btn.disabled = true;
  btn.textContent = 'Extracting details…';

  try {
    const res = await apiFetch('/api/narrative', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    const data = await res.json();
    S.narrative = data.narrative;
    S.slots     = data.slots;
    S.warnings  = data.warnings;
    renderReview();
    goTo(4);
  } catch (e) {
    toast(`Extraction failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Extract restoration details →';
  }
});

// ---------------------------------------------------------------------------
// Step 4 — Review
// ---------------------------------------------------------------------------
const SLOT_META = [
  ['casing_cut_depth_ft', 'Casing cut depth'],
  ['cap_type',            'Cap type'],
  ['cellar_filled',       'Cellar filled'],
  ['equipment_removed',   'Equipment removed'],
  ['vegetation_action',   'Vegetation'],
  ['grading_action',      'Grading'],
  ['date_of_work',        'Date of work'],
  ['surface_owner_consent','Surface owner'],
];

function renderReview() {
  // Slots
  el('slots-grid').innerHTML = SLOT_META.map(([key, label]) => {
    const val    = S.slots[key];
    const filled = val !== null && val !== undefined && val !== false && val !== '';
    const disp   = Array.isArray(val)
      ? (val.length ? val.join(', ') : null)
      : (val === true ? 'Yes' : val);
    return `
      <div class="slot-card ${filled && disp ? 'ok' : 'gap'}">
        <span class="slot-lbl">${label}</span>
        <span class="slot-val">${filled && disp ? disp : '—'}</span>
      </div>`;
  }).join('');

  // Narrative
  el('narrative-edit').value = S.narrative;

  // Warnings
  const warnBox = el('warn-box');
  if (S.warnings.length) {
    warnBox.innerHTML = S.warnings
      .map(w => `<div class="warn-item">⚠ ${w}</div>`)
      .join('');
    show(warnBox);
  } else {
    hide(warnBox);
  }

  // Default cert date to today
  if (!el('cert-date').value) {
    el('cert-date').value = new Date().toISOString().slice(0, 10);
  }
}

el('btn-generate').addEventListener('click', async () => {
  const sigName  = el('sig-name').value.trim();
  const sigTitle = el('sig-title').value.trim() || 'Operator Representative';
  const certDate = el('cert-date').value;
  const plugDate = S.slots.date_of_work || certDate;

  if (!sigName)  { toast('Enter your name before generating.'); return; }
  if (!certDate) { toast('Enter the certification date.'); return; }

  const btn = el('btn-generate');
  btn.disabled = true;
  btn.textContent = 'Generating PDF…';

  const payload = {
    api_number:               S.apiNumber || '42-000-00000',
    operator_signature_name:  sigName,
    operator_title:           sigTitle,
    certification_date:       certDate,
    plugging_date:            plugDate || certDate,
    buqw_depth_ft:            S.buqwDepth,
    gau_letter_reference:     S.gauRef,
    narrative:                el('narrative-edit').value.trim(),
    paid_tier:                false,
  };

  try {
    const authH = (window.PlugfileAuth && window.PlugfileAuth.authHeaders())
                  || {};
    const res  = await apiFetch('/api/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', ...authH },
      body:    JSON.stringify(payload),
    });
    const blob = await res.blob();

    if (S.pdfUrl) URL.revokeObjectURL(S.pdfUrl);
    S.pdfUrl      = URL.createObjectURL(blob);
    S.pdfFilename = `W3_${S.apiNumber.replace(/-/g, '')}_DRAFT.pdf`;

    el('download-link').href     = S.pdfUrl;
    el('download-link').download = S.pdfFilename;

    loadDistrictOffice();
    goTo(5);
  } catch (e) {
    toast(`PDF generation failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate W-3 PDF →';
  }
});

// Resolve and render the RRC district office this filing goes to.
async function loadDistrictOffice() {
  const box = el('district-office');
  const api = S.apiNumber;
  if (!api || api === '42-000-00000') { hide(box); return; }

  try {
    const res = await apiFetch('/api/district-office', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_number: api }),
    });
    const r = await res.json();
    if (!r.matched || !r.office) { hide(box); return; }
    const o = r.office;
    const fax = o.fax ? `<div class="result-row"><span class="rlabel">Fax</span><span>${esc(o.fax)}</span></div>` : '';
    box.innerHTML = `
      <div class="result-row">
        <span class="rlabel">File with</span>
        <span class="hi">${esc(o.name)} District Office</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Address</span>
        <span>${esc(o.address_line1)}, ${esc(o.city_state_zip)}</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Phone</span>
        <span>${esc(o.phone)}</span>
      </div>
      ${fax}
      <div class="result-row">
        <span class="rlabel">Email</span>
        <span>${esc(o.email)}</span>
      </div>`;
    show(box);
  } catch (e) {
    hide(box);   // routing is advisory — never block the download
  }
}

// ---------------------------------------------------------------------------
// Step 5 — Start over
// ---------------------------------------------------------------------------
el('btn-restart').addEventListener('click', () => {
  if (S.pdfUrl) { URL.revokeObjectURL(S.pdfUrl); }
  Object.assign(S, {
    step: 1, apiNumber: '', wellData: null,
    buqwDepth: null, gauRef: null, transcript: '',
    narrative: '', slots: {}, warnings: [], pdfUrl: null,
    aorFindings: [], aorGuidanceLoaded: false,
  });
  el('api-number').value = '';
  el('transcript').value = '';
  el('gau-upload-label').textContent = 'Tap to upload GAU letter PDF';
  hide(el('well-result'));
  hide(el('gau-result'));
  hide(el('gau-verdict'));
  hide(el('manual-buqw-group'));
  hide(el('warn-box'));
  hide(el('district-office'));
  // Reset AOR helper + step-1 buttons.
  hide(el('aor-panel'));
  hide(el('aor-body'));
  hide(el('aor-results'));
  el('aor-guidance').innerHTML = '';
  el('aor-results').innerHTML = '';
  show(el('btn-lookup'));
  show(el('btn-skip-lookup'));
  hide(el('btn-well-continue'));
  el('btn-step2-next').disabled = true;
  finalText = '';
  goTo(1);
});

// ---------------------------------------------------------------------------
// Save / resume hooks (used by saves.js when signed in)
// ---------------------------------------------------------------------------
window.toast = toast;
window.PlugfileWizard = {
  formType: 'w3',
  title: () => `W-3 ${S.apiNumber || 'draft'}`,
  getState: () => ({
    api: S.apiNumber, step: S.step,
    buqwDepth: S.buqwDepth, gauRef: S.gauRef,
    transcript: el('transcript').value, narrative: S.narrative,
    slots: S.slots, warnings: S.warnings,
    sigName: el('sig-name').value, sigTitle: el('sig-title').value,
    certDate: el('cert-date').value,
  }),
  restore: (d) => {
    S.apiNumber = d.api || '';
    S.buqwDepth = d.buqwDepth ?? null;
    S.gauRef = d.gauRef ?? null;
    S.narrative = d.narrative || '';
    S.slots = d.slots || {};
    S.warnings = d.warnings || [];
    if (el('api-number')) el('api-number').value = d.api || '';
    if (el('transcript')) el('transcript').value = d.transcript || '';
    if (el('sig-name')) el('sig-name').value = d.sigName || '';
    if (el('sig-title')) el('sig-title').value = d.sigTitle || 'Operator Representative';
    if (el('cert-date')) el('cert-date').value = d.certDate || '';
    if (S.slots && Object.keys(S.slots).length) renderReview();
    goTo(d.step >= 1 && d.step <= 5 ? d.step : 1);
  },
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
goTo(1);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(console.warn);
}
