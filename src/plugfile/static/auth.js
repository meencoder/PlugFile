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
  const S = { enabled: false, supabase: null, session: null };
  const PROVIDERS = [['google', 'Google'], ['facebook', 'Facebook'],
                     ['apple', 'Apple'], ['email', 'Email']];

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

  async function signIn(provider) {
    if (!S.supabase) return;
    if (provider === 'email') {
      const email = window.prompt('Enter your email for a one-time sign-in link:');
      if (!email) return;
      const { error } = await S.supabase.auth.signInWithOtp({
        email, options: { emailRedirectTo: location.href },
      });
      window.alert(error ? ('Error: ' + error.message)
                         : 'Check your email for the sign-in link.');
    } else {
      await S.supabase.auth.signInWithOAuth({
        provider, options: { redirectTo: location.href },
      });
    }
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
      bar.innerHTML = `<span class="auth-lbl">Sign in:</span>`
        + PROVIDERS.map(([p, label]) =>
            `<button class="auth-btn" data-p="${p}">${label}</button>`).join('');
      bar.querySelectorAll('button[data-p]').forEach(b =>
        b.onclick = () => signIn(b.dataset.p));
    }
    bar.classList.remove('hidden');
    // Let the save/resume module react to the signed-in state.
    if (window.PlugfileSaves && window.PlugfileSaves.refresh) {
      window.PlugfileSaves.refresh();
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
