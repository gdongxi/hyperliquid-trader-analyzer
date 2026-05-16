# Hyperliquid Trader Analyzer

A Python tool that fetches on-chain trader data from Hyperliquid's public API, scores each trader using a multi-factor model, and outputs a ranked leaderboard of copy-trading candidates.

Built as part of the research behind an AI-powered copy trading agent for the [Agora Agents Hackathon](https://agora.thecanteenapp.com/) — focused on on-chain strategy evaluation and USDC settlement via Circle's developer stack on Arc.

---

## How it works

The analyzer pulls trader data from Hyperliquid's leaderboard endpoint and scores each trader across five factors:

| Factor | Weight | Description |
|---|---|---|
| Sharpe Ratio | 30% | Risk-adjusted returns |
| Win Rate | 20% | Percentage of profitable trades |
| ROI | 20% | Total return on investment |
| Max Drawdown | 15% | Peak-to-trough loss (penalty) |
| Volume (30d) | 15% | Consistency of activity |

Each factor is min-max normalized to `[0, 1]` before weighting. Drawdown is applied as a penalty — higher drawdown reduces the final score.

---

## Quickstart

```bash
git clone https://github.com/gdongxi/hyperliquid-trader-analyzer
cd hyperliquid-trader-analyzer
pip install -r requirements.txt
python main.py
```

### Options

```bash
python main.py --top 10              # show top 10 traders
python main.py --window week         # use weekly leaderboard
python main.py --no-save             # skip JSON export
```

### Example output

```
🏆  Hyperliquid Trader Leaderboard — Copy-Trading Candidates

Rank  Name                  Score      ROI    Win%   MaxDD   Sharpe    PnL (USD)
--------------------------------------------------------------------------------
1     ArbitrageKing         0.847    142.3%   71.2%  12.4%     3.21   $1,240,500
2     SteadyHands           0.821     89.5%   68.9%   8.1%     2.87     $430,200
3     DeltaNeutral          0.798     76.2%   65.3%  10.7%     2.54     $318,900
...
```

Results are also exported to `data/results.json`.

---

## Project structure

```
hyperliquid-trader-analyzer/
├── src/
│   └── analyzer.py        # core logic: API client, scorer, parser, reporter
├── tests/
│   └── test_analyzer.py   # unit tests for scoring model and parser
├── data/                  # output directory for JSON results
├── main.py                # CLI entry point
├── requirements.txt
└── README.md
```

---

## Scoring model details

### Why these factors?

**Sharpe Ratio (30%)** is the primary signal. Raw ROI is easy to game with high leverage — Sharpe penalizes volatility and rewards consistent returns.

**Win Rate (20%)** filters out traders who win big on a few bets but lose consistently. Sustained copy-trading requires predictable performance.

**ROI (20%)** matters but is weighted lower than Sharpe to avoid selecting high-risk, high-reward traders that blow up followers.

**Max Drawdown (15% penalty)** is critical for copy-trading. A follower who enters during a drawdown phase experiences the full loss without the preceding gains.

**Volume (15%)** filters out inactive accounts. A trader with great historical stats but no recent activity may have retired the strategy.

### Limitations & production improvements

The Hyperliquid leaderboard endpoint doesn't expose win rate, drawdown, or Sharpe directly. This tool uses heuristic estimates based on available fields. For production use, fetch `userFills` per trader to compute exact values from the trade history.

---

## Running tests

```bash
python -m pytest tests/ -v
```

---

## Roadmap

- [ ] Exact Sharpe computation from `userFills` daily return series
- [ ] Strategy drift detection (rolling window comparison)
- [ ] Slash-bonded performance bond integration via Circle / Arc smart contracts
- [ ] REST API wrapper for integration with copy-trading execution layer

---

## Related

This tool is part of a larger system being built for the [Agora Agents Hackathon](https://agora.thecanteenapp.com/) — an AI-powered copy trading agent that uses Circle's Wallets, Gateway, and USDC settlement on Arc.

---

## License

MIT
