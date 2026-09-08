// Which company a typed query refers to, decided by rule rather than by guess.
//
// This is the one place in the import that can put the WRONG security's price
// target into a client report, so it is kept apart from the fetching, written
// to be read, and tested. The spec is explicit: never silently choose among
// multiple share classes, ADRs, foreign listings, funds, or similarly named
// issuers. Everything below exists to honour that while still resolving the
// ordinary case -- a ticker -- without asking anyone anything.
//
// Loaded by background.js as a module and by tests/select.test.js under node.

// A ticker as typed: two to six letters, optionally a dot-suffixed class
// ("BRK.B"). Anything longer, spaced, or mixed with punctuation is a company
// name or a question, and is not treated as a ticker.
const TICKER = /^[A-Z]{1,6}(?:\.[A-Z])?$/;

/**
 * The ticker a prompt is about, or "" when it does not lead with one.
 *
 * The box accepts "AAPL", "Apple", and "NVDA - is this a good entry?", and the
 * provider itself tells a user who typed something unresolvable to "try
 * leading with just the ticker". So the first token is where a ticker will be
 * if there is one; a prompt that opens with a word is left to say so.
 */
export function tickerFromPrompt(prompt) {
  const first = String(prompt || "").trim().split(/[\s,;:]+/)[0] || "";
  const upper = first.toUpperCase();
  // Case matters: "Apple" is a name that happens to be short, "AAPL" is a
  // ticker. Requiring the typed form to already be upper-case is what keeps
  // the two apart without a securities master to consult.
  return first === upper && TICKER.test(upper) ? upper : "";
}

/** The ticker part of a J.P. Morgan company id: "AAPL.O" and "GOOGL@US" -> "AAPL", "GOOGL". */
export function idTicker(id) {
  return String(id || "").split(/[.@]/)[0].toUpperCase();
}

// A US primary listing. J.P. Morgan suffixes Reuters-style: ".O" is NASDAQ,
// ".N" is NYSE. "@US" is the same company quoted on a foreign line -- Alphabet
// in euros -- which is a different instrument and not what a US ticker means.
const US_PRIMARY = /\.[ONA]$/i;

/**
 * The one company a query resolves to, or null when that cannot be decided.
 *
 * Returning null is a real answer, not a failure to try: the report then simply
 * carries no view from this house and says so, which is correct and recoverable.
 * Putting Apple Hospitality's price target under Apple's name is neither.
 *
 * @param {Array} candidates suggestions from the portal, COMPANY-typed or not
 * @param {string} query what the user typed
 * @returns {{id: string, label: string}|null}
 */
export function selectCompany(candidates, query) {
  const companies = (candidates || []).filter(
    (c) => c && c.type === "COMPANY" && c.id
  );
  if (companies.length === 0) return null;
  if (companies.length === 1) return { id: companies[0].id, label: companies[0].label || "" };

  const ticker = tickerFromPrompt(query);
  if (!ticker) {
    // A name matched several issuers and there is no ticker to settle it.
    // "Apple" reaching both Apple and Apple Hospitality REIT is exactly the
    // case the spec refuses to have decided silently.
    return null;
  }

  const exact = companies.filter((c) => idTicker(c.id) === ticker);
  if (exact.length === 0) return null;
  if (exact.length === 1) return { id: exact[0].id, label: exact[0].label || "" };

  // Same ticker on more than one line -- "GOOGL" is both GOOGL.O and the euro
  // GOOGL@US. A US ticker means the US primary listing, so prefer it, but only
  // when exactly one candidate is one; two US listings for one ticker is not a
  // state we can resolve and is not one we will invent an answer for.
  const primary = exact.filter((c) => US_PRIMARY.test(c.id));
  return primary.length === 1 ? { id: primary[0].id, label: primary[0].label || "" } : null;
}
