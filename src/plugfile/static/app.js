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
};

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

    setTimeout(() => goTo(2), 700);
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

  try {
    const res = await apiFetch('/api/gau', { method: 'POST', body: form });
    const data = await res.json();
    S.buqwDepth = data.buqw_depth_ft;
    S.gauRef    = data.gau_letter_reference;

    const specials = data.special_requirements.length
      ? `<div class="result-row sp"><span class="rlabel">⚠ Special</span><span>${data.special_requirements.join('; ')}</span></div>`
      : '';

    el('gau-result').innerHTML = `
      <div class="result-row">
        <span class="rlabel">BUQW Depth</span>
        <span class="hi">${data.buqw_depth_ft.toLocaleString()} ft</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Reference</span>
        <span>${data.gau_letter_reference}</span>
      </div>
      <div class="result-row">
        <span class="rlabel">Type</span>
        <span>${data.letter_type}</span>
      </div>
      ${specials}`;
    show(el('gau-result'));
    lbl.textContent = file.name + ' ✓';
    el('btn-step2-next').disabled = false;
  } catch (err) {
    toast(`Could not parse GAU letter: ${err.message}`);
    lbl.textContent = 'Tap to upload GAU letter PDF';
    showManualBuqw();
  }
});

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
    const res  = await apiFetch('/api/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });
    const blob = await res.blob();

    if (S.pdfUrl) URL.revokeObjectURL(S.pdfUrl);
    S.pdfUrl      = URL.createObjectURL(blob);
    S.pdfFilename = `W3_${S.apiNumber.replace(/-/g, '')}_DRAFT.pdf`;

    el('download-link').href     = S.pdfUrl;
    el('download-link').download = S.pdfFilename;

    goTo(5);
  } catch (e) {
    toast(`PDF generation failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate W-3 PDF →';
  }
});

// ---------------------------------------------------------------------------
// Step 5 — Start over
// ---------------------------------------------------------------------------
el('btn-restart').addEventListener('click', () => {
  if (S.pdfUrl) { URL.revokeObjectURL(S.pdfUrl); }
  Object.assign(S, {
    step: 1, apiNumber: '', wellData: null,
    buqwDepth: null, gauRef: null, transcript: '',
    narrative: '', slots: {}, warnings: [], pdfUrl: null,
  });
  el('api-number').value = '';
  el('transcript').value = '';
  el('gau-upload-label').textContent = 'Tap to upload GAU letter PDF';
  hide(el('well-result'));
  hide(el('gau-result'));
  hide(el('manual-buqw-group'));
  hide(el('warn-box'));
  el('btn-step2-next').disabled = true;
  finalText = '';
  goTo(1);
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
goTo(1);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(console.warn);
}
