// The only path between the app's page and the part of this extension that can
// reach the portal.
//
// WHY A CONTENT SCRIPT rather than letting the page message the extension
// directly: an unpacked extension is given a fresh id every time it is loaded,
// so a page holding that id would need it re-pasted after every reinstall. This
// runs inside the app's own page instead -- only on the origins the manifest
// names -- so the page talks to `window` and never has to know an id at all.
//
// It relays, and does nothing else. It reads no page content, and it passes on
// one field: the prompt the advisor typed.

const TAG_REQUEST = "jpmm-view-request";
const TAG_RESPONSE = "jpmm-view-response";
const TAG_READY = "jpmm-extension-ready";

window.addEventListener("message", (event) => {
  // Same page only. A frame the app embedded, or anything posting in from
  // elsewhere, is not the app asking.
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data;
  if (!data || data.tag !== TAG_REQUEST) return;

  chrome.runtime.sendMessage(
    { tag: "jpmm-view", prompt: String(data.prompt || "") },
    (reply) => {
      // A worker that failed to wake leaves lastError set and reply undefined.
      // Reported as a plain failure rather than thrown: the page treats a
      // missing view as "no house view", which is the correct outcome here.
      const error = chrome.runtime.lastError;
      window.postMessage(
        {
          tag: TAG_RESPONSE,
          id: data.id,
          reply: error ? { ok: false, reason: "failed", detail: "extension unavailable" } : reply,
        },
        location.origin
      );
    }
  );
});

// Announced once, so the page can tell an installed extension from an absent
// one and stop waiting on a reply that is never coming.
window.postMessage({ tag: TAG_READY }, location.origin);
