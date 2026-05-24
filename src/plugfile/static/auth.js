'use strict';
// ===========================================================================
// Plugfile auth (frontend) — managed provider via Supabase, graceful open mode.
//
//   * Fetches /api/auth/config. If auth is disabled (no provider configured),
//     this is a complete no-op: no UI, no token, the app stays an open form.
//   * If enabled with Supabase config, loads the Supabase JS SDK and offers
//     Google / Facebook / Apple / email (magic-link) sign-in.
//   * Exposes window.PlugfileAuth.authHeaders() so the wizards attach a Bearer
//     token to gated calls (e.g. the final/paid PDF).
//
// To enable, set on the server: PLUGFILE_AUTH_JWKS_URL, PLUGFILE_SUPABASE_URL,
// PLUGFILE_SUPABASE_ANON_KEY, PLUGFILE_AUTH_PROVIDER=supabase. The anon key is
// public by design; never expose the service-role key or JWT secret.
// ===========================================================================
(function () {
  const S = { enabled: false, supabase: null, session: null, ext: null };
  const PROVIDERS = [['google', 'Google'], ['facebook', 'Facebook'],
                     ['apple', 'Apple'], ['email', 'Email']];

  function notify(msg, ok) {
    if (typeof window.toast === 'function') return window.toast(msg, ok ? 'ok' : 'error');
    window.alert(msg);
  }
  function plabel(p) { const f = PROVIDERS.find((x) => x[0] === p); return f ? f[1] : p; }

  function loadScript(src) {
    return new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = src; s.onload = res; s.onerror = () => rej(new Error('load ' + src));
      document.head.appendChild(s);
    });
  }

  function authHeaders() {
    const t = S.session && S.session.access_token;
    return t ? { Authorization: 'Bearer ' + t } : {};
  }

  const redirectUrl = () => location.origin + location.pathname;

  async function signIn(provider) {
    if (!S.supabase) return;
    if (provider === 'email') {
      const email = window.prompt('Enter your email for a one-time sign-in link:');
      if (!email) return;
      const { error } = await S.supabase.auth.signInWithOtp({
        email, options: { emailRedirectTo: redirectUrl() },
      });
      notify(error ? ('Email sign-in failed: ' + error.message)
                   : 'Check your email for the sign-in link.', !error);
      return;
    }
    // Guard: a disabled provider would otherwise redirect to a raw Supabase
    // 400 ("provider is not enabled"). Stop early with a clear message.
    if (S.ext && S.ext[provider] === false) {
      notify(plabel(provider) + ' sign-in isn’t enabled yet — an admin must turn it on in '
        + 'Supabase → Authentication → Providers.', false);
      return;
    }
    const { data, error } = await S.supabase.auth.signInWithOAuth({
      provider, options: { redirectTo: redirectUrl(), skipBrowserRedirect: true },
    });
    if (error || !(data && data.url)) {
      notify(plabel(provider) + ' sign-in failed: ' + ((error && error.message) || 'no redirect URL'), false);
      return;
    }
    window.location.href = data.url;
  }

  async function signOut() {
    if (S.supabase) { await S.supabase.auth.signOut(); S.session = null; render(); }
  }

  function render() {
    const bar = document.getElementById('auth-bar');
    if (!bar) return;
    const u = S.session && S.session.user;
    if (u) {
      bar.innerHTML = `<span class="auth-email">${(u.email || 'signed in')}</span>`
        + `<button class="auth-btn" id="auth-out">Sign out</button>`;
      bar.querySelector('#auth-out').onclick = signOut;
    } else {
      // Only offer providers actually enabled in Supabase (falls back to all
      // if the settings probe failed). No dead buttons.
      const avail = PROVIDERS.filter(([p]) => !S.ext || S.ext[p] === true);
      const list = avail.length ? avail : PROVIDERS;
      bar.innerHTML = `<span class="auth-lbl">Sign in:</span>`
        + list.map(([p, label]) =>
            `<button class="auth-btn" data-p="${p}">${label}</button>`).join('');
      bar.querySelectorAll('button[data-p]').forEach(b =>
        b.onclick = () => signIn(b.dataset.p));
    }
    bar.classList.remove('hidden');
    // Let the save/resume + rules-monitor modules react to the signed-in state.
    if (window.PlugfileSaves && window.PlugfileSaves.refresh) {
      window.PlugfileSaves.refresh();
    }
    if (window.PlugfileRules && window.PlugfileRules.refresh) {
      window.PlugfileRules.refresh();
    }
  }

  async function init() {
    let cfg;
    try { cfg = await (await fetch('/api/auth/config')).json(); }
    catch (e) { return; }                 // API unreachable — stay open
    if (!cfg.enabled) return;             // open mode — no auth UI
    if (!(cfg.supabase_url && cfg.supabase_anon_key)) {
      console.warn('Auth enabled but no Supabase client config returned.');
      return;
    }
    try {
      await loadScript('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2');
      S.supabase = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);
      // Probe which auth providers are actually enabled so we only show those.
      try {
        const r = await fetch(cfg.supabase_url.replace(/\/$/, '') + '/auth/v1/settings',
          { headers: { apikey: cfg.supabase_anon_key } });
        const j = await r.json();
        S.ext = (j && j.external) ? j.external : null;
        const off = S.ext ? ['google', 'facebook', 'apple', 'email'].filter((p) => S.ext[p] === false) : [];
        if (off.length) console.info('[Plugfile auth] disabled providers (enable in '
          + 'Supabase → Authentication → Providers): ' + off.join(', '));
      } catch (_) { S.ext = null; }
      const { data } = await S.supabase.auth.getSession();
      S.session = data.session;
      S.enabled = true;
      S.supabase.auth.onAuthStateChange((_evt, sess) => { S.session = sess; render(); });
      render();
    } catch (e) {
      console.warn('Supabase auth init failed:', e);
    }
  }

  window.PlugfileAuth = {
    authHeaders,
    isEnabled: () => S.enabled,
    user: () => S.session && S.session.user,
    client: () => S.supabase,
    signIn, signOut,
  };
  init();
})();
