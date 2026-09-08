// The bookmarklet the advisor clicks on a J.P. Morgan Markets company page.
//
// WHAT IT DOES. Reads the company id out of the address bar, asks the portal's
// own endpoints for the figures behind the page, takes the rendered text for
// the few fields those endpoints do not carry, and hands the lot to this app
// in a new tab. The app shows it for checking; saving stays a separate,
// deliberate act.
//
// WHY IT RUNS HERE. The portal's endpoints answer only to the page's own
// origin, so nothing outside the browser can call them -- and the app, which
// runs in a container, has no session to call them with. This runs where the
// advisor already is, signed in under their own entitlement, on a page already
// open in front of them.
//
// WHAT IT WILL NOT SEND. The payload is assembled field by field below, and
// every field is evidence. No cookie, token, header or other session material
// is read or forwarded -- the server refuses a payload carrying anything
// shaped like one, so a change here that broke that rule would fail loudly
// rather than leak quietly.
//
// %APP_ORIGIN% is substituted for this app's own origin when the install page
// builds the link, so the hand-off is addressed to exactly one destination.
(function () {
  var APP = '%APP_ORIGIN%';
  var HOUSE = 'J.P. Morgan';
  var TEXT_LIMIT = 40000;   // the server's own cap; trimmed here so it is not refused

  var companyId = new URLSearchParams(location.search).get('companyId') || '';
  if (!companyId) {
    alert('Open a company page first — this reads the company shown in the address bar.');
    return;
  }

  // Opened before anything is fetched. A window opened after an await has lost
  // the click that justified it, and the popup blocker takes it.
  var tab = window.open(APP + '/house-views.html#import', 'tag_house_import');
  if (!tab) {
    alert('Allow pop-ups for this page, then click again — the import opens in a new tab.');
    return;
  }

  function json(path) {
    return fetch(path, { credentials: 'include', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  // The company panel lives inside two nested frames and the top document
  // carries none of its text. Rather than name those frames -- ids a restyle
  // would change -- take the longest text found at any depth, which is the
  // panel by a wide margin.
  function deepText(doc, depth) {
    var best = '';
    try {
      var root = doc.querySelector('main') || doc.body;
      if (root && root.innerText) { best = root.innerText; }
    } catch (e) { /* a frame we cannot reach simply contributes nothing */ }
    if (depth > 0) {
      var frames = [];
      try { frames = doc.querySelectorAll('iframe'); } catch (e) { frames = []; }
      for (var i = 0; i < frames.length; i++) {
        var sub = '';
        try {
          sub = frames[i].contentDocument ? deepText(frames[i].contentDocument, depth - 1) : '';
        } catch (e) { sub = ''; }
        if (sub.length > best.length) { best = sub; }
      }
    }
    return best;
  }

  Promise.all([
    json('/research/company/' + encodeURIComponent(companyId) + '/earning-strip'),
    json('/research/company/' + encodeURIComponent(companyId) + '/equity-estimates')
  ]).then(function (results) {
    var strip = (results[0] && results[0].data) || {};
    var estimates = (results[1] && results[1].data) || {};
    var text = deepText(document, 3).slice(0, TEXT_LIMIT);

    var payload = {
      house: HOUSE,
      ticker: String(strip.ticker || '').slice(0, 16),
      company_id: companyId.slice(0, 40),
      locator: location.href.slice(0, 500),
      strip: Array.isArray(strip.earningStrip) ? strip.earningStrip : [],
      estimates: Array.isArray(estimates.equityEstimates) ? estimates.equityEstimates : [],
      text: text
    };

    if (!payload.strip.length && !payload.text.trim()) {
      alert('Nothing readable on this page. If it is still loading, let it finish and click again.');
      tab.close();
      return;
    }

    // The app announces itself when it is ready; only then is anything sent,
    // and only to the one origin this link was built for.
    var sent = false;
    function onReady(event) {
      if (event.origin !== APP || !event.data || event.data.tag !== 'tag-import-ready') { return; }
      if (sent) { return; }
      sent = true;
      window.removeEventListener('message', onReady);
      tab.postMessage({ tag: 'tag-import', payload: payload }, APP);
    }
    window.addEventListener('message', onReady);

    setTimeout(function () {
      if (!sent) {
        window.removeEventListener('message', onReady);
        alert('The Technical Analyst Agent tab did not answer. Check it is open and unlocked, then click again.');
      }
    }, 20000);
  });
})();
