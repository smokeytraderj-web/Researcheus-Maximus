// Run: node --test extension/tests/
//
// The candidate sets below are what the portal actually returned for these
// queries, captured from a signed-in session -- not invented shapes.

import test from "node:test";
import assert from "node:assert/strict";
import { selectCompany, tickerFromPrompt, idTicker } from "../select.js";

const AXON = [
  { label: "Axon", type: "COMPANY", id: "AXON.O" },
  { label: "AXON", type: "FREE_TEXT", id: "FREE_TEXT_SEARCH" },
  { label: "AXON", type: "TITLE_MATCH", id: "TITLE_MATCH" },
];
const ALPHABET = [
  { label: "Alphabet", type: "COMPANY", id: "GOOG.O" },
  { label: "Alphabet Inc.", type: "COMPANY", id: "GOOGL.O" },
  { label: "Alphabet (€)", type: "COMPANY", id: "GOOGL@US" },
];
const APPLE = [
  { label: "Apple", type: "COMPANY", id: "AAPL.O" },
  { label: "Apple Hospitality REIT, Inc.", type: "COMPANY", id: "APLE.N" },
];
const TESLA = [{ label: "Tesla Inc", type: "COMPANY", id: "TSLA.O" }];

test("a single company is taken", () => {
  assert.equal(selectCompany(AXON, "AXON").id, "AXON.O");
  assert.equal(selectCompany(TESLA, "TSLA").id, "TSLA.O");
});

test("non-company suggestions are never selected", () => {
  // Free-text and title matches come back for every query and are not securities.
  const onlyNoise = AXON.filter((c) => c.type !== "COMPANY");
  assert.equal(selectCompany(onlyNoise, "AXON"), null);
});

test("a ticker settles a query that matched several issuers", () => {
  assert.equal(selectCompany(ALPHABET, "GOOGL").id, "GOOGL.O");
  assert.equal(selectCompany(ALPHABET, "GOOG").id, "GOOG.O");
  assert.equal(selectCompany(APPLE, "AAPL").id, "AAPL.O");
});

test("the foreign line never wins over the US listing for a US ticker", () => {
  // GOOGL is both GOOGL.O and the euro-quoted GOOGL@US. They are different
  // instruments; a US ticker means the US one.
  assert.equal(selectCompany(ALPHABET, "GOOGL").id, "GOOGL.O");
});

test("a name matching several issuers resolves to nothing rather than the first", () => {
  // The report then carries no view from this house and says so. Apple
  // Hospitality's price target under Apple's name is the outcome being refused.
  assert.equal(selectCompany(APPLE, "Apple"), null);
  assert.equal(selectCompany(ALPHABET, "Alphabet"), null);
});

test("a ticker that matches none of the candidates resolves to nothing", () => {
  assert.equal(selectCompany(APPLE, "MSFT"), null);
});

test("no candidates at all is not an error, just nothing", () => {
  assert.equal(selectCompany([], "ZZZQQQ"), null);
  assert.equal(selectCompany(null, "ZZZQQQ"), null);
});

test("a ticker is read off the front of a real prompt", () => {
  assert.equal(tickerFromPrompt("AXON"), "AXON");
  assert.equal(tickerFromPrompt("NVDA - is this a good entry point?"), "NVDA");
  assert.equal(tickerFromPrompt("TSLA, should I add here"), "TSLA");
  assert.equal(tickerFromPrompt("  MSFT  "), "MSFT");
  assert.equal(tickerFromPrompt("BRK.B"), "BRK.B");
});

test("a company name is not mistaken for a ticker", () => {
  // Case is what separates them without a securities master to consult.
  assert.equal(tickerFromPrompt("Apple"), "");
  assert.equal(tickerFromPrompt("Alphabet Inc"), "");
  assert.equal(tickerFromPrompt("should I buy Tesla"), "");
  assert.equal(tickerFromPrompt(""), "");
  assert.equal(tickerFromPrompt(null), "");
});

test("the ticker part of an id is read off either suffix style", () => {
  assert.equal(idTicker("AAPL.O"), "AAPL");
  assert.equal(idTicker("GOOGL@US"), "GOOGL");
  assert.equal(idTicker("APLE.N"), "APLE");
  assert.equal(idTicker(""), "");
});
