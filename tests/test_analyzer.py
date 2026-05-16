"""
Unit tests for the multi-factor scoring model.
Run: python -m pytest tests/ -v
"""

import pytest
from src.analyzer import TraderStats, TraderScorer, ScoringWeights, parse_leaderboard_row


def make_trader(**kwargs) -> TraderStats:
    defaults = dict(
        address="0xabc",
        display_name="TestTrader",
        account_value=50000,
        total_pnl=10000,
        roi=0.2,
        win_rate=0.6,
        volume_30d=200000,
        max_drawdown=0.1,
        sharpe_ratio=1.5,
    )
    defaults.update(kwargs)
    return TraderStats(**defaults)


class TestTraderScorer:

    def test_higher_sharpe_scores_better(self):
        scorer = TraderScorer()
        good = make_trader(address="0x1", sharpe_ratio=3.0, display_name="Good")
        bad  = make_trader(address="0x2", sharpe_ratio=0.2, display_name="Bad")
        ranked = scorer.score_all([good, bad])
        assert ranked[0].display_name == "Good"

    def test_higher_drawdown_scores_worse(self):
        scorer = TraderScorer()
        safe   = make_trader(address="0x1", max_drawdown=0.05, display_name="Safe")
        risky  = make_trader(address="0x2", max_drawdown=0.80, display_name="Risky")
        ranked = scorer.score_all([safe, risky])
        assert ranked[0].display_name == "Safe"

    def test_scores_between_zero_and_one(self):
        scorer  = TraderScorer()
        traders = [make_trader(address=f"0x{i}", display_name=f"T{i}") for i in range(5)]
        ranked  = scorer.score_all(traders)
        for t in ranked:
            assert 0.0 <= t.score <= 1.0

    def test_ranks_assigned_correctly(self):
        scorer  = TraderScorer()
        traders = [make_trader(address=f"0x{i}", display_name=f"T{i}",
                               sharpe_ratio=float(i)) for i in range(1, 6)]
        ranked  = scorer.score_all(traders)
        assert ranked[0].rank == 1
        assert ranked[-1].rank == 5

    def test_custom_weights(self):
        weights = ScoringWeights(sharpe=0.0, win_rate=1.0, roi=0.0, drawdown=0.0, volume=0.0)
        scorer  = TraderScorer(weights=weights)
        high_wr = make_trader(address="0x1", win_rate=0.9, display_name="HighWR")
        low_wr  = make_trader(address="0x2", win_rate=0.3, display_name="LowWR")
        ranked  = scorer.score_all([high_wr, low_wr])
        assert ranked[0].display_name == "HighWR"


class TestParser:

    def _make_row(self, pnl=5000, roi=0.25, vlm=100000, account=20000):
        return {
            "ethAddress": "0xdeadbeef",
            "displayName": "Trader1",
            "accountValue": str(account),
            "windowItems": [{"pnl": str(pnl), "roi": str(roi), "vlm": str(vlm)}],
        }

    def test_parses_valid_row(self):
        row    = self._make_row()
        trader = parse_leaderboard_row(row)
        assert trader is not None
        assert trader.total_pnl == 5000
        assert trader.roi == 0.25

    def test_returns_none_on_bad_data(self):
        result = parse_leaderboard_row({})
        assert result is None

    def test_display_name_fallback(self):
        row = self._make_row()
        row["displayName"] = None
        trader = parse_leaderboard_row(row)
        assert "..." in trader.display_name
