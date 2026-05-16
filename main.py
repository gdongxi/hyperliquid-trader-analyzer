#!/usr/bin/env python3
"""
Hyperliquid Trader Analyzer — CLI entry point

Usage:
  python main.py                        # top 20, allTime window
  python main.py --top 10 --window week
  python main.py --no-save              # skip JSON export
"""

import argparse
from src.analyzer import run

def main():
    parser = argparse.ArgumentParser(
        description="Score and rank Hyperliquid traders for copy-trading."
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top traders to display (default: 20)"
    )
    parser.add_argument(
        "--window", choices=["day", "week", "month", "allTime"],
        default="allTime",
        help="Leaderboard time window (default: allTime)"
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Skip saving results to JSON"
    )
    args = parser.parse_args()
    run(top_n=args.top, window=args.window, save=not args.no_save)

if __name__ == "__main__":
    main()
