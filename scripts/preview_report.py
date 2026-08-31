"""Dev-only shortcut: render a report and open it immediately.

Skips the Home -> intake -> horizon -> Evidence Review click-through entirely
and goes straight to the finished interactive report, for fast iteration on
report design. Uses the deterministic demo provider (no live sources, no
credentials) unless --live is passed. Never used by the shipped app.

Usage:
    python3 scripts/preview_report.py [TICKER] [--horizon short|medium|long|all]
        [--question "..."] [--live]
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.models import Horizon, ResearchRequest  # noqa: E402
from services.research_runner import ResearchRunner  # noqa: E402

_HORIZONS = {
    "short": Horizon.SHORT,
    "medium": Horizon.MEDIUM,
    "long": Horizon.LONG,
    "all": Horizon.ALL,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", default="AXON")
    parser.add_argument("--horizon", choices=sorted(_HORIZONS), default="medium")
    parser.add_argument("--question", default="")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use LiveResearchProvider instead of the demo provider (requires network access and any configured API keys).",
    )
    args = parser.parse_args()

    if args.live:
        from research.live_provider import LiveResearchProvider

        runner = ResearchRunner(provider=LiveResearchProvider())
    else:
        runner = ResearchRunner()

    request = ResearchRequest(
        query=args.ticker,
        horizon=_HORIZONS[args.horizon],
        question=args.question or f"What does the current evidence say about {args.ticker}?",
    )
    prepared = runner.prepare(request)
    output_dir = Path(__file__).resolve().parents[1] / "output" / "preview"
    final_html = runner.finalize(prepared, output_dir)
    print(f"Report ready: {final_html}")
    webbrowser.open(final_html.as_uri())


if __name__ == "__main__":
    main()
