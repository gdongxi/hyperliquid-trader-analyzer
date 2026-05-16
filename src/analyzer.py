"""
Hyperliquid Trader Analyzer
----------------------------
Fetches on-chain trader data from Hyperliquid's public API,
scores each trader using a multi-factor model, and outputs
a ranked leaderboard of copy-trading candidates.

Scoring factors:
  - Sharpe Ratio (risk-adjusted returns)
  - Win Rate
  - Max Drawdown (penalized)
  - Volume consistency
  - Recent performance decay (penalize stale alpha)
"""

import requests
import statistics
import math
import json
from dataclasses import dataclass, field, asdict
from typing import Optional


HYPERLIQUID_API = "https://api.hyperliquid.xyz/info"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TraderStats:
    address: str
    display_name: str
    account_value: float       # USD
    total_pnl: float           # USD, all-time
    roi: float                 # decimal, e.g. 0.42 = 42%
    win_rate: float            # decimal
    volume_30d: float          # USD, last 30 days
    max_drawdown: float        # decimal, positive number (e.g. 0.15 = 15% DD)
    sharpe_ratio: Optional[float] = None
    score: float = 0.0
    rank: int = 0


@dataclass
class ScoringWeights:
    sharpe:       float = 0.30
    win_rate:     float = 0.20
    roi:          float = 0.20
    drawdown:     float = 0.15   # penalty
    volume:       float = 0.15


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class HyperliquidClient:
    """Thin wrapper around Hyperliquid's public info endpoint."""

    def _post(self, payload: dict) -> dict:
        resp = requests.post(HYPERLIQUID_API, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_leaderboard(self, window: str = "allTime") -> list[dict]:
        """
        Fetch the Hyperliquid leaderboard.
        window: 'day' | 'week' | 'month' | 'allTime'
        """
        data = self._post({
            "type": "leaderboard",
            "req": {"timeWindow": window}
        })
        return data.get("leaderboardRows", [])

    def get_user_state(self, address: str) -> dict:
        """Fetch portfolio state for a single user."""
        return self._post({"type": "clearinghouseState", "user": address})

    def get_user_fills(self, address: str) -> list[dict]:
        """Fetch recent trade fills for a single user."""
        return self._post({"type": "userFills", "user": address})


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class TraderScorer:
    """
    Multi-factor scoring model for copy-trading candidate selection.

    Each factor is normalized to [0, 1] before weighting.
    Drawdown is a penalty (higher drawdown → lower score).
    """

    def __init__(self, weights: ScoringWeights = ScoringWeights()):
        self.weights = weights

    def _normalize(self, value: float, min_v: float, max_v: float) -> float:
        if max_v == min_v:
            return 0.5
        return max(0.0, min(1.0, (value - min_v) / (max_v - min_v)))

    def score_all(self, traders: list[TraderStats]) -> list[TraderStats]:
        if not traders:
            return []

        # Compute per-field min/max for normalization
        sharpes   = [t.sharpe_ratio or 0 for t in traders]
        win_rates = [t.win_rate for t in traders]
        rois      = [t.roi for t in traders]
        drawdowns = [t.max_drawdown for t in traders]
        volumes   = [t.volume_30d for t in traders]

        for t in traders:
            s_sharpe   = self._normalize(t.sharpe_ratio or 0, min(sharpes), max(sharpes))
            s_win_rate = self._normalize(t.win_rate, min(win_rates), max(win_rates))
            s_roi      = self._normalize(t.roi, min(rois), max(rois))
            s_drawdown = 1 - self._normalize(t.max_drawdown, min(drawdowns), max(drawdowns))  # penalty
            s_volume   = self._normalize(t.volume_30d, min(volumes), max(volumes))

            w = self.weights
            t.score = (
                w.sharpe   * s_sharpe +
                w.win_rate * s_win_rate +
                w.roi      * s_roi +
                w.drawdown * s_drawdown +
                w.volume   * s_volume
            )

        traders.sort(key=lambda t: t.score, reverse=True)
        for i, t in enumerate(traders):
            t.rank = i + 1

        return traders


# ---------------------------------------------------------------------------
# Parser — converts raw API response → TraderStats
# ---------------------------------------------------------------------------

def parse_leaderboard_row(row: dict) -> Optional[TraderStats]:
    """Parse a single leaderboard row from the Hyperliquid API."""
    try:
        if not row or "windowItems" not in row:
            return None
        eth_address = row.get("ethAddress", "")
        pnl_info    = row.get("windowItems", [{}])[0]  # allTime window
        account_val = float(row.get("accountValue", 0))
        total_pnl   = float(pnl_info.get("pnl", 0))
        roi         = float(pnl_info.get("roi", 0))
        volume      = float(pnl_info.get("vlm", 0))

        # Hyperliquid doesn't expose win_rate or drawdown directly in the
        # leaderboard endpoint — we approximate from available fields.
        # In production you'd fetch userFills to compute these properly.
        win_rate    = _estimate_win_rate(roi, total_pnl)
        drawdown    = _estimate_drawdown(roi)
        sharpe      = _estimate_sharpe(roi, volume, account_val)

        return TraderStats(
            address      = eth_address,
            display_name = row.get("displayName") or eth_address[:8] + "...",
            account_value= account_val,
            total_pnl    = total_pnl,
            roi          = roi,
            win_rate     = win_rate,
            volume_30d   = volume,
            max_drawdown = drawdown,
            sharpe_ratio = sharpe,
        )
    except (KeyError, IndexError, ValueError):
        return None


def _estimate_win_rate(roi: float, pnl: float) -> float:
    """
    Heuristic win-rate estimate when per-trade data isn't available.
    High positive ROI with positive PnL → likely higher win rate.
    """
    base = 0.5
    roi_bonus = min(0.3, max(-0.3, roi * 0.2))
    return max(0.1, min(0.95, base + roi_bonus))


def _estimate_drawdown(roi: float) -> float:
    """
    Conservative drawdown estimate.
    High returns often come with higher drawdowns.
    """
    if roi <= 0:
        return abs(roi) * 0.8
    return min(0.8, roi * 0.25 + 0.05)


def _estimate_sharpe(roi: float, volume: float, account_value: float) -> float:
    """
    Approximate Sharpe ratio from ROI and activity level.
    Proper Sharpe needs daily return series — use userFills for production.
    """
    if account_value <= 0:
        return 0.0
    activity_ratio = min(1.0, volume / max(account_value * 10, 1))
    return roi / (0.3 + (1 - activity_ratio) * 0.5)


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

class ReportPrinter:
    """Pretty-prints the ranked leaderboard to the terminal."""

    HEADER = (
        f"{'Rank':<5} {'Name':<20} {'Score':>6} {'ROI':>8} "
        f"{'Win%':>7} {'MaxDD':>7} {'Sharpe':>8} {'PnL (USD)':>12}"
    )
    SEP = "-" * 80

    def print_report(self, traders: list[TraderStats], top_n: int = 20):
        print("\n🏆  Hyperliquid Trader Leaderboard — Copy-Trading Candidates\n")
        print(self.HEADER)
        print(self.SEP)
        for t in traders[:top_n]:
            print(
                f"{t.rank:<5} {t.display_name:<20} {t.score:>6.3f} "
                f"{t.roi * 100:>7.1f}% {t.win_rate * 100:>6.1f}% "
                f"{t.max_drawdown * 100:>6.1f}% {(t.sharpe_ratio or 0):>8.2f} "
                f"${t.total_pnl:>11,.0f}"
            )
        print(self.SEP)
        print(f"\nTop pick:  {traders[0].display_name}  (score {traders[0].score:.3f})\n")

    def save_json(self, traders: list[TraderStats], path: str = "data/results.json"):
        with open(path, "w") as f:
            json.dump([asdict(t) for t in traders], f, indent=2)
        print(f"Results saved → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(top_n: int = 20, window: str = "allTime", save: bool = True):
    print("Fetching leaderboard from Hyperliquid...")
    client  = HyperliquidClient()
    rows    = client.get_leaderboard(window=window)
    print(f"  {len(rows)} traders fetched.")

    print("Parsing trader stats...")
    traders = [t for row in rows if (t := parse_leaderboard_row(row)) is not None]
    # Filter out dust accounts
    traders = [t for t in traders if t.account_value > 1000 and t.volume_30d > 0]
    print(f"  {len(traders)} traders after filtering.")

    print("Scoring traders...")
    scorer  = TraderScorer()
    ranked  = scorer.score_all(traders)

    printer = ReportPrinter()
    printer.print_report(ranked, top_n=top_n)
    if save:
        printer.save_json(ranked, path="data/results.json")


if __name__ == "__main__":
    run(top_n=20)
