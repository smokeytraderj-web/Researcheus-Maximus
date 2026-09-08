// Reads the rendered company panel, in whichever frame it turns out to be in.
//
// WHY A DECLARED CONTENT SCRIPT rather than chrome.scripting.executeScript:
// the panel lives two frames down, and injecting into a frame that is still
// settling failed silently and returned the 300 characters of the site's own
// nav menu -- or nothing. Chrome places a declared script into every matching
// frame itself, including nested ones, and does it at the right moment. Same
// mechanism as bridge.js, which has never had this problem.
//
// WHY IT ASKS FIRST. This runs in every frame of every J.P. Morgan Markets page
// the advisor opens, including pages they are reading for themselves. It sends
// nothing until the worker confirms this is the tab it opened for an import, so
// ordinary browsing is never read and never transmitted.

const PANEL_MIN = 2000;   // the nav menu runs ~250; the panel runs to five figures

function panelText() {
  // body, not main: the frames here do carry a <main>, and it is empty. Reading
  // it in preference to the body is what returned the nav menu as "the page".
  return (document.body && document.body.innerText) || "";
}

chrome.runtime.sendMessage({ tag: "jpmm-reader-hello" }, (answer) => {
  if (chrome.runtime.lastError || !answer || !answer.read) return;

  // Polled, because "load" fires long before this panel paints and how long it
  // takes varies. Each frame reports its own best; the worker keeps the longest.
  const deadline = Date.now() + 30000;
  const tick = () => {
    const text = panelText();
    if (text.length > PANEL_MIN) {
      chrome.runtime.sendMessage({ tag: "jpmm-page-text", text: text.slice(0, 40000) });
      return;
    }
    if (Date.now() < deadline) setTimeout(tick, 700);
  };
  tick();
});
