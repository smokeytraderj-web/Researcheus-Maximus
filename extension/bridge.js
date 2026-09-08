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
const TAG_PING = "jpmm-extension-ping";
const TAG_READY = "jpmm-extension-ready";

function announce() {
  window.postMessage({ tag: TAG_READY }, location.origin);
}

window.addEventListener("message", (event) => {
  // Same page only. A frame the app embedded, or anything posting in from
  // elsewhere, is not the app asking.
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data;
  if (!data) return;

  // Answering a ping is what actually establishes contact. This script runs at
  // document_start, before the page's own script has parsed, so an unsolicited
  // announcement arrives while nothing is listening yet and is simply lost --
  // which left the page believing no extension was installed no matter how many
  // times it was reinstalled. The page asks; this answers; the race is gone.
  if (data.tag === TAG_PING) {
    announce();
    return;
  }

  if (data.tag !== TAG_REQUEST) return;

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

// Still announced unprompted, for the case where the page's listener is already
// up -- a soft navigation, or this script injected into a live page. The ping
// above is what makes it reliable; this only makes it faster.
announce();
document.addEventListener("DOMContentLoaded", announce);
