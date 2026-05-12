#!/usr/bin/env python3
"""
LLM Agent Loop Cost Calculator with graphing.

Compute expected cost and cache statistics for an LLM agent loop
for a given number of turns, and generate visualizations over time.
"""

import argparse
import random
import sys
from pathlib import Path

# EXAMPLE RUN
# python3 scripts/cost_calculator.py -p 0.14 -c 0.0028 -o 0.28 -n 30 -i 1000 -r 2000 -a 1000 -u 1000
# --- Core calculation --------------------------------------------------------


def compute_turn_breakdown(
    it: int,  # Initial input tokens (system + first user message)
    rt: int,  # Average response / reasoning tokens per turn
    ao: int,  # Average output tokens per turn
    n: int,  # Number of turns
    au: int = 0,  # Always-uncached tokens per turn (injected reminders, etc.)
    rt_range: tuple[float, float] = (
        1.0,
        1.0,
    ),  # Random multiplier range for response tokens (min, max)
    ao_range: tuple[float, float] = (
        1.0,
        1.0,
    ),  # Random multiplier range for output tokens (min, max)
):
    """Return per-turn token counts for cache hit, cache miss, and output."""
    if n < 1:
        raise ValueError("Number of turns (n) must be >= 1")

    ao = ao or rt  # if ao is 0, fall back to rt so the model works

    rt_min, rt_max = rt_range
    ao_min, ao_max = ao_range

    turns = []
    prev_response = 0  # previous turn's total response (ao + rt), used as next turn's cache miss
    cumulative_input = 0

    for turn in range(1, n + 1):
        # Randomize per-turn values if ranges specify variance
        rt_factor = random.uniform(rt_min, rt_max)
        ao_factor = random.uniform(ao_min, ao_max)
        actual_rt = max(1, round(rt * rt_factor))
        actual_ao = max(1, round(ao * ao_factor))

        if turn == 1:
            hit = 0
            miss = it + au
            cumulative_input = it
        else:
            hit = cumulative_input  # previous cumulative context is a cache hit
            miss = prev_response + au  # previous turn's response + always-uncached
            cumulative_input = hit + prev_response  # add previous response to cumulative

        prev_response = actual_ao + actual_rt

        turns.append(
            {
                "turn": turn,
                "cumulative_input": cumulative_input,
                "cache_hit": hit,
                "cache_miss": miss,
                "output": actual_ao,
            }
        )

    return turns


def compute_agent_loop_costs(
    cmp: float,  # Cache Miss Token Price  (per token)
    chp: float,  # Cache Hit Token Price   (per token)
    op: float,  # Output Token Price      (per token)
    it: int,  # Initial input tokens
    rt: int,  # Average response / reasoning tokens per turn
    ao: int,  # Average output tokens per turn
    n: int,  # Number of turns
    au: int = 0,  # Always-uncached tokens per turn (injected reminders, etc.)
    rt_range: tuple[float, float] = (1.0, 1.0),  # Random multiplier range for response tokens
    ao_range: tuple[float, float] = (1.0, 1.0),  # Random multiplier range for output tokens
):
    """
    Compute expected cost and cache statistics for an LLM agent loop.
    """
    turns = compute_turn_breakdown(it, rt, ao, n, au=au, rt_range=rt_range, ao_range=ao_range)

    # Accumulate across turns
    total_hit = sum(t["cache_hit"] for t in turns)
    total_miss = sum(t["cache_miss"] for t in turns)
    total_input = total_hit + total_miss
    total_output = sum(t["output"] for t in turns)

    cost_cmp = cmp * total_miss
    cost_chp = chp * total_hit
    cost_op = op * total_output
    total_cost = cost_cmp + cost_chp + cost_op

    cache_hit_ratio = total_hit / (total_hit + total_miss) if (total_hit + total_miss) > 0 else 0.0

    # Per-turn costs
    turn_costs = []
    cum_cost = 0.0
    for t in turns:
        tc = chp * t["cache_hit"] + cmp * t["cache_miss"] + op * t["output"]
        cum_cost += tc
        turn_cost = {
            "turn": t["turn"],
            "cost_cache_hit": round(chp * t["cache_hit"], 6),
            "cost_cache_miss": round(cmp * t["cache_miss"], 6),
            "cost_output": round(op * t["output"], 6),
            "cost_total": round(tc, 6),
            "cost_cumulative": round(cum_cost, 6),
            "input_tokens": t["cache_hit"] + t["cache_miss"],
            "cache_hit": t["cache_hit"],
            "cache_miss": t["cache_miss"],
            "output": t["output"],
            "cache_hit_ratio": (
                round(t["cache_hit"] / (t["cache_hit"] + t["cache_miss"]), 6)
                if (t["cache_hit"] + t["cache_miss"])
                else 0.0
            ),
        }
        turn_costs.append(turn_cost)

    return {
        "total_cost": round(total_cost, 6),
        "cost_breakdown": {
            "cache_miss": round(cost_cmp, 6),
            "cache_hit": round(cost_chp, 6),
            "output": round(cost_op, 6),
        },
        "token_counts": {
            "total_input": total_input,
            "total_output": total_output,
            "cache_hit": total_hit,
            "cache_miss": total_miss,
        },
        "cache_hit_ratio": round(cache_hit_ratio, 6),
        "turns": turn_costs,
    }


# --- Graphing -----------------------------------------------------------------


def _check_imports():
    """Ensure plotting libraries are available; return False if not."""
    try:
        import matplotlib  # noqa: F401
        import numpy as np  # noqa: F401

        return True
    except ImportError:
        return False


def plot_cost_accumulation(result: dict, output_path: str | Path = "cost_accumulation.png"):
    """Plot cumulative cost growth over turns."""
    import matplotlib.pyplot as plt

    turns = result["turns"]
    turn_nums = [t["turn"] for t in turns]
    cum_costs = [t["cost_cumulative"] for t in turns]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(turn_nums, cum_costs, marker="o", linestyle="-", linewidth=2, color="#1f77b4")
    ax.fill_between(turn_nums, cum_costs, alpha=0.15, color="#1f77b4")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Cumulative Cost ($)")
    ax.set_title("Total Cost Accumulation Over Turns")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_cost_breakdown(result: dict, output_path: str | Path = "cost_breakdown.png"):
    """Stacked area chart of per-turn costs (cache miss, cache hit, output)."""
    import matplotlib.pyplot as plt
    import numpy as np

    turns = result["turns"]
    turn_nums = [t["turn"] for t in turns]

    miss_costs = np.array([t["cost_cache_miss"] for t in turns])
    hit_costs = np.array([t["cost_cache_hit"] for t in turns])
    out_costs = np.array([t["cost_output"] for t in turns])

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.stackplot(
        turn_nums,
        miss_costs,
        hit_costs,
        out_costs,
        labels=["Cache Miss (input)", "Cache Hit (input)", "Output"],
        colors=["#d62728", "#2ca02c", "#ff7f0e"],
        alpha=0.85,
    )
    ax.set_xlabel("Turn")
    ax.set_ylabel("Cost per Turn ($)")
    ax.set_title("Per-Turn Cost Breakdown")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_cache_hit_ratio(result: dict, output_path: str | Path = "cache_hit_ratio.png"):
    """Plot cache hit ratio per turn and overall."""
    import matplotlib.pyplot as plt

    turns = result["turns"]
    turn_nums = [t["turn"] for t in turns]
    per_turn_ratios = [t["cache_hit_ratio"] for t in turns]
    overall = result["cache_hit_ratio"]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(turn_nums, per_turn_ratios, marker="s", linestyle="-", linewidth=2, color="#9467bd")
    ax.axhline(y=overall, color="gray", linestyle="--", alpha=0.7, label=f"Overall: {overall:.1%}")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Cache Hit Ratio")
    ax.set_title("Cache Hit Ratio Over Turns")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def plot_all(result: dict, prefix: str = "agent_loop"):
    """Generate all three plots in a single 2x2 figure."""
    import matplotlib.pyplot as plt
    import numpy as np

    turns = result["turns"]
    turn_nums = [t["turn"] for t in turns]
    cum_costs = [t["cost_cumulative"] for t in turns]
    per_turn_ratios = [t["cache_hit_ratio"] for t in turns]
    miss_costs = np.array([t["cost_cache_miss"] for t in turns])
    hit_costs = np.array([t["cost_cache_hit"] for t in turns])
    out_costs = np.array([t["cost_output"] for t in turns])
    overall = result["cache_hit_ratio"]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    # Top-left: cost accumulation
    ax = axes[0, 0]
    ax.plot(turn_nums, cum_costs, marker="o", linestyle="-", linewidth=2, color="#1f77b4")
    ax.fill_between(turn_nums, cum_costs, alpha=0.15, color="#1f77b4")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Cumulative Cost ($)")
    ax.set_title("Total Cost Accumulation")
    ax.grid(True, alpha=0.3)

    # Top-right: cache hit ratio
    ax = axes[0, 1]
    ax.plot(turn_nums, per_turn_ratios, marker="s", linestyle="-", linewidth=2, color="#9467bd")
    ax.axhline(y=overall, color="gray", linestyle="--", alpha=0.7, label=f"Overall: {overall:.1%}")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Cache Hit Ratio")
    ax.set_title("Cache Hit Ratio")
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax.legend(fontsize="small")
    ax.grid(True, alpha=0.3)

    # Bottom: stacked cost breakdown
    ax = axes[1, 0]
    ax.stackplot(
        turn_nums,
        miss_costs,
        hit_costs,
        out_costs,
        labels=["Cache Miss", "Cache Hit", "Output"],
        colors=["#d62728", "#2ca02c", "#ff7f0e"],
        alpha=0.85,
    )
    ax.set_xlabel("Turn")
    ax.set_ylabel("Cost per Turn ($)")
    ax.set_title("Per-Turn Cost Breakdown")
    ax.legend(loc="upper left", fontsize="small")
    ax.grid(True, alpha=0.3)

    # Bottom-right: input token growth
    ax = axes[1, 1]
    input_tokens = [t["input_tokens"] for t in turns]
    hit_tokens = [t["cache_hit"] for t in turns]
    ax.bar(turn_nums, input_tokens, color="#8c8c8c", alpha=0.4, label="Total input")
    ax.bar(turn_nums, hit_tokens, color="#2ca02c", alpha=0.7, label="Cache hit portion")
    ax.set_xlabel("Turn")
    ax.set_ylabel("Tokens")
    ax.set_title("Input Token Growth")
    ax.legend(loc="upper left", fontsize="small")
    ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle(
        f"Agent Loop Cost Analysis — {len(turns)} turns, ${result['total_cost']:.4f} total",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    path = f"{prefix}_overview.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


# --- CLI ----------------------------------------------------------------------


def format_turn_table(result: dict) -> str:
    """Format a textual table of per-turn data."""
    lines = []
    lines.append(
        f"{'Turn':>5} {'Input Tokens':>14} {'Cache Hit':>10} {'Cache Miss':>12} {'Output':>8} "
        f"{'Hit %':>7} {'Turn Cost':>10} {'Cum. Cost':>10}"
    )
    lines.append("─" * 80)
    for t in result["turns"]:
        lines.append(
            f"{t['turn']:>5} {t['input_tokens']:>14,} {t['cache_hit']:>10,} {t['cache_miss']:>12,} {t['output']:>8,} "
            f"{t['cache_hit_ratio']:>6.1%} {t['cost_total']:>9.6f} {t['cost_cumulative']:>9.6f}"
        )
    lines.append("─" * 80)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute expected cost of an LLM agent loop with prompt caching."
    )
    parser.add_argument(
        "-p",
        "--price-cache-miss",
        type=float,
        default=3.0,
        help="Cache miss token price (per 1 million tokens, default: 3.0)",
    )

    parser.add_argument(
        "-c",
        "--price-cache-hit",
        type=float,
        default=0.30,
        help="Cache hit token price (per 1 million tokens, default: 0.30)",
    )

    parser.add_argument(
        "-o",
        "--price-output",
        type=float,
        default=15.0,
        help="Output token price (per 1 million tokens, default: 15.0)",
    )

    parser.add_argument(
        "-i",
        "--initial-tokens",
        type=int,
        default=500,
        help="Initial input tokens (system + first user message, default: 500)",
    )
    parser.add_argument(
        "-r",
        "--response-tokens",
        type=int,
        default=300,
        help="Average response / reasoning tokens per turn (default: 300)",
    )
    parser.add_argument(
        "-a",
        "--output-tokens",
        type=int,
        default=0,
        help="Average output tokens per turn (default: same as --response-tokens)",
    )
    parser.add_argument(
        "-n",
        "--turns",
        type=int,
        default=10,
        help="Number of turns (default: 10)",
    )
    parser.add_argument(
        "--no-graphs",
        action="store_true",
        help="Skip generating graphs",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Directory to save graph images (default: current directory)",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="agent_loop",
        help="Filename prefix for graph images (default: agent_loop)",
    )
    parser.add_argument(
        "-u",
        "--always-uncached",
        type=int,
        default=0,
        help="Always-uncached tokens per turn (reminder messages, etc., default: 0)",
    )
    parser.add_argument(
        "--rt-range",
        type=str,
        default="1,1",
        help="Random multiplier range for response tokens (min,max, default: 1,1)",
    )
    parser.add_argument(
        "--ao-range",
        type=str,
        default="1,1",
        help="Random multiplier range for output tokens (min,max, default: 1,1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (default: not set)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Prices are per 1 million tokens — convert to per-token
    cmp = args.price_cache_miss / 1_000_000
    chp = args.price_cache_hit / 1_000_000
    op = args.price_output / 1_000_000

    it = args.initial_tokens
    rt = args.response_tokens
    ao = args.output_tokens or rt
    au = args.always_uncached
    n = args.turns

    # Parse range arguments
    def _parse_range(s: str) -> tuple[float, float]:
        parts = [float(x.strip()) for x in s.split(",")]
        if len(parts) != 2:
            raise ValueError(f"Range must be 'min,max', got '{s}'")
        return (parts[0], parts[1])

    rt_range = _parse_range(args.rt_range)
    ao_range = _parse_range(args.ao_range)

    if args.seed is not None:
        random.seed(args.seed)

    result = compute_agent_loop_costs(
        cmp, chp, op, it, rt, ao, n, au=au, rt_range=rt_range, ao_range=ao_range
    )

    # ── Print summary ─────────────────────────────────────────────────────────
    print("=" * 58)
    print("  LLM Agent Loop Cost Analysis")
    print("=" * 58)
    print("  Parameters:")
    print(f"    Turns:                {n}")
    print(f"    Initial tokens:       {it:,}")
    print(f"    Response tokens/turn: {rt:,}")
    print(f"    Output tokens/turn:   {ao:,}")
    print(f"    Always-uncached/turn: {au:,}")
    print(f"    Cache miss price:     ${args.price_cache_miss:.2f}/1M")
    print(f"    Cache hit price:      ${args.price_cache_hit:.2f}/1M")
    print(f"    Output price:         ${args.price_output:.2f}/1M")
    print()
    print("  Results:")
    print(f"    Total cost:          ${result['total_cost']:.6f}")
    print(f"    Cache hit ratio:     {result['cache_hit_ratio']:.1%}")
    print(f"    Total input tokens:  {result['token_counts']['total_input']:,}")
    print(f"      Cache hit:         {result['token_counts']['cache_hit']:,}")
    print(f"      Cache miss:        {result['token_counts']['cache_miss']:,}")
    print(f"    Total output tokens: {result['token_counts']['total_output']:,}")
    print()

    breakdown = result["cost_breakdown"]
    print("  Cost Breakdown:")
    print(f"    Cache miss (input):  ${breakdown['cache_miss']:.6f}")
    print(f"    Cache hit (input):   ${breakdown['cache_hit']:.6f}")
    print(f"    Output:              ${breakdown['output']:.6f}")
    print()

    print("  Per-Turn Detail:")
    print(format_turn_table(result))
    print()

    # ── Graphs ────────────────────────────────────────────────────────────────
    if not args.no_graphs:
        if not _check_imports():
            print("  [SKIP] matplotlib not available — install with: pip install matplotlib")
        else:
            out_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
            out_dir.mkdir(parents=True, exist_ok=True)
            prefix = str(out_dir / args.prefix)

            paths = []
            paths.append(plot_cost_accumulation(result, f"{prefix}_cost_accumulation.png"))
            paths.append(plot_cost_breakdown(result, f"{prefix}_cost_breakdown.png"))
            paths.append(plot_cache_hit_ratio(result, f"{prefix}_cache_hit_ratio.png"))
            paths.append(plot_all(result, prefix))

            print("  Graphs saved:")
            for p in paths:
                print(f"    {p}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
