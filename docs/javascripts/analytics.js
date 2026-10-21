/* Optional documentation analytics. No Google request is made before opt-in. */
(() => {
  'use strict';
  const measurementId = 'G-WJSBVPS5RV';
  const base = '/loxilbdocs-inference-gateway/';
  const storageKey = 'igw_analytics_consent_v1';
  // Local builds, forks and other projects on the shared Pages host never collect.
  const production = location.protocol === 'https:' && location.hostname === 'loxilb-io.github.io' &&
    location.pathname.startsWith(base);
  if (!production && !['localhost', '127.0.0.1'].includes(location.hostname)) return;
  const privacySignal = navigator.globalPrivacyControl === true || navigator.doNotTrack === '1';
  let started = false;
  let choice = null;
  try { choice = localStorage.getItem(storageKey); } catch (_) { /* No persistent choice. */ }

  function page() {
    // The build-generated canonical URL identifies a public document. Never use query or fragment.
    const canonical = document.querySelector('link[rel="canonical"]');
    const url = new URL(canonical ? canonical.href : location.origin + base);
    if (url.origin !== location.origin || !url.pathname.startsWith(base)) return null;
    return url.origin + url.pathname;
  }
  function referrer() {
    try { return document.referrer ? new URL(document.referrer).origin + '/' : ''; }
    catch (_) { return ''; }
  }
  function start() {
    if (started || privacySignal || !production || !page()) return;
    started = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('consent', 'default', {
      analytics_storage: 'granted', ad_storage: 'denied',
      ad_user_data: 'denied', ad_personalization: 'denied'
    });
    window.gtag('js', new Date());
    window.gtag('config', measurementId, {
      send_page_view: false, page_location: page(), page_referrer: referrer(),
      page_title: document.title, allow_google_signals: false,
      allow_ad_personalization_signals: false, cookie_domain: 'none',
      cookie_path: base, cookie_expires: 0
    });
    window.gtag('event', 'page_view', {page_location: page(), page_referrer: referrer()});
    const script = document.createElement('script');
    script.async = true;
    script.referrerPolicy = 'no-referrer';
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + measurementId;
    document.head.appendChild(script);
  }
  function choose(value) {
    try { localStorage.setItem(storageKey, value); } catch (_) { /* Current page only. */ }
    choice = value;
    if (value === 'granted') start();
    else if (started) {
      window['ga-disable-' + measurementId] = true;
      window.gtag('consent', 'update', {analytics_storage: 'denied'});
      // Remove only this integration's host-only GA cookies within its own path.
      for (const entry of document.cookie.split(';')) {
        const name = entry.split('=')[0].trim();
        if (name === '_ga' || name === '_ga_WJSBVPS5RV') {
          document.cookie = name + '=; Max-Age=0; Path=' + base + '; SameSite=Lax; Secure';
        }
      }
    }
    panel.hidden = true;
  }
  const panel = document.createElement('section');
  panel.className = 'igw-analytics-consent';
  panel.setAttribute('aria-label', 'Optional analytics');
  panel.innerHTML = '<p>Allow optional Google Analytics to help improve these docs? ' +
    'Google receives usage events only after you accept. Search text and URL query strings are excluded. ' +
    '<a href="' + base + 'privacy/">Privacy details</a></p>' +
    '<button type="button" data-choice="granted">Accept analytics</button> ' +
    '<button type="button" data-choice="denied">Reject analytics</button>';
  panel.hidden = privacySignal || choice === 'granted' || choice === 'denied';
  panel.querySelectorAll('button').forEach(button => {
    button.addEventListener('click', () => choose(button.dataset.choice));
  });
  document.body.appendChild(panel);
  const settings = document.createElement('button');
  settings.type = 'button';
  settings.className = 'igw-analytics-settings';
  settings.textContent = 'Analytics preferences';
  settings.addEventListener('click', () => {
    if (privacySignal) {
      settings.textContent = 'Analytics disabled by your browser privacy signal';
      return;
    }
    // Reload after a prior withdrawal so the Google disable flag cannot be bypassed.
    if (started && choice === 'denied') { location.reload(); return; }
    panel.hidden = false;
  });
  document.body.appendChild(settings);
  if (choice === 'granted') start();
})();
