// Fetches a company's published J.P. Morgan view, in the advisor's own session.
//
// WHY THIS EXISTS AT ALL. The portal's endpoints answer only to requests from
// markets.jpmorgan.com, carrying the entitlement of whoever is signed in there.
// The app runs on a server that has no such session and must never hold one, so
// nothing server-side can ask. This runs inside the advisor's browser, beside
// the session they signed into themselves, and asks the portal exactly what the
// company page asks it when they open that page by hand.
//
// WHAT IT NEVER TOUCHES. No cookie, token or credential is read here. Chrome
// attaches the session to these requests because of the host permission above;
// this code never sees it, never stores it, and never forwards it. What is
// handed back to the page is the figures, and only the figures -- see the
// explicit payload built in `viewFor`. There is no chrome.cookies permission in
// the manifest, so this could not read one if it tried.
//
// WHAT IT WILL NOT DECIDE. Which security a query means, when that is genuinely
// ambiguous. See select.js: the rule refuses rather than guesses, and a refusal
// leaves the report with no view from this house rather than the wrong one.

import { selectCompany, tickerFromPrompt } from "./select.js";

const PORTAL = "https://markets.jpmorgan.com";

// The portal's own typeahead query, as its search box issues it.
const SUGGEST = `query getSuggestions($userInput: String) {
  searchService {
    suggest(text: $userInput, count: 8, includeTextSuggestions: TRUE, includePageSuggestions: TRUE, includeAISearchSuggestions: TRUE, includeSearchV2Properties: TRUE, includeCompanyTargetPrice: TRUE) {
      label type id
    }
  }
}`;

/** A signed-out session is answered with a login page, not an error status. */
class SignedOut extends Error {}

async function portalJson(path, init) {
  const response = await fetch(PORTAL + path, {
    credentials: "include",
    ...init,
    headers: { Accept: "application/json", ...((init && init.headers) || {}) },
  });
  const type = response.headers.get("content-type") || "";
  // Signed out, the portal redirects to sign-on and the fetch follows it, so a
  // 200 carrying HTML is the shape a lost session actually takes. Treating that
  // as "no data" would report the company as uncovered; it is not, we are just
  // no longer allowed to ask.
  if (!type.includes("json")) throw new SignedOut();
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return response.json();
}

async function resolveCompany(query) {
  const body = {
    operationName: "getSuggestions",
    variables: { userInput: tickerFromPrompt(query) || String(query || "").trim() },
    query: SUGGEST,
  };
  const data = await portalJson("/research/controller/graphql/query-v2", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const suggestions = ((data.data || {}).searchService || {}).suggest || [];
  return selectCompany(suggestions, query);
}

// Read inside the page, in every frame, by chrome.scripting. Declared as a
// plain function because it is serialised and injected -- it closes over
// nothing here and must not.
function readPageText() {
  const root = document.querySelector("main") || document.body;
  return root ? root.innerText : "";
}

/**
 * The company page's rendered text, taken from a tab the advisor never sees.
 *
 * The numbers all come from JSON above. This is for the four things no endpoint
 * serves -- sector, region, the covering analyst, and the latest note. The
 * note matters most: it carries the date the view was published, and without
 * it a saved view has no date at all. Dating it "today" because that is when it
 * was fetched would make a call from two months ago read as this morning's,
 * which is the one thing this whole feature must not do.
 *
 * Returns "" on any failure. The strip still stands; the server then reports
 * the note fields missing by name rather than inventing them.
 */
async function pageText(companyId) {
  let tab = null;
  try {
    tab = await chrome.tabs.create({
      url: `${PORTAL}/jpmm/research.browse.company?companyId=${encodeURIComponent(companyId)}`,
      active: false,   // opens behind whatever the advisor is looking at
    });
    await new Promise((resolve) => {
      const done = setTimeout(resolve, 20000);   // never hang the import on a slow page
      const listener = (id, info) => {
        if (id === tab.id && info.status === "complete") {
          chrome.tabs.onUpdated.removeListener(listener);
          clearTimeout(done);
          // The panel renders after load, inside two nested frames.
          setTimeout(resolve, 3500);
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
    });
    // allFrames because the top document carries none of the panel's text.
    // The longest result is the company panel by a wide margin.
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: readPageText,
    });
    return results
      .map((r) => (r && typeof r.result === "string" ? r.result : ""))
      .reduce((longest, text) => (text.length > longest.length ? text : longest), "")
      .slice(0, 40000);   // the server's own cap
  } catch (error) {
    return "";
  } finally {
    if (tab && tab.id) {
      try { await chrome.tabs.remove(tab.id); } catch (e) { /* already gone */ }
    }
  }
}

async function viewFor(query) {
  const company = await resolveCompany(query);
  if (!company) return { ok: false, reason: "no-match" };

  const id = encodeURIComponent(company.id);
  const [strip, estimates] = await Promise.all([
    portalJson(`/research/company/${id}/earning-strip`),
    portalJson(`/research/company/${id}/equity-estimates`).catch(() => null),
  ]);
  const stripData = (strip && strip.data) || {};
  const rows = Array.isArray(stripData.earningStrip) ? stripData.earningStrip : [];
  if (!rows.length) return { ok: false, reason: "no-coverage", company: company.id };

  // Assembled field by field, so what leaves this worker is a closed set that
  // can be read off the page. Nothing is spread in from a response wholesale.
  return {
    ok: true,
    payload: {
      house: "J.P. Morgan",
      ticker: String(stripData.ticker || "").slice(0, 16),
      company_id: company.id.slice(0, 40),
      locator: `${PORTAL}/jpmm/research.browse.company?companyId=${company.id}`,
      strip: rows.map((r) => ({
        label: String((r && r.label) || ""),
        value: String((r && r.value) === undefined || (r && r.value) === null ? "" : r.value),
        currency: String((r && r.currency) || ""),
      })),
      estimates: (((estimates || {}).data || {}).equityEstimates || []).map((e) => ({
        displayName: String((e && e.displayName) || ""),
        dataItems: Object.fromEntries(
          Object.entries((e && e.dataItems) || {}).map(([period, cell]) => [
            String(period),
            { displayValue: String(((cell || {}).displayValue) ?? "") },
          ])
        ),
      })),
      // Sector, region, the analyst and the latest note, which no endpoint
      // serves. Empty when the page could not be read; the server then names
      // those as missing instead of filling them in.
      text: await pageText(company.id),
    },
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only this extension's own bridge may ask, and the manifest runs that bridge
  // only on the app's origins -- so the origin check lives there, in the one
  // place a page can reach, rather than being restated here where it would
  // drift out of step with it.
  if (sender.id !== chrome.runtime.id) return false;
  if (!message || message.tag !== "jpmm-view") return false;

  viewFor(String(message.prompt || ""))
    .then(sendResponse)
    .catch((error) => {
      sendResponse(
        error instanceof SignedOut
          ? { ok: false, reason: "signed-out" }
          // The message, never the object: an exception's own fields can carry
          // request detail, and this crosses back to a page.
          : { ok: false, reason: "failed", detail: String(error.message || "").slice(0, 200) }
      );
    });
  return true;   // keeps the channel open for the async reply
});
