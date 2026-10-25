"""Run every condition, save raw results, a summary table and figures.

Usage:  python src/run_experiment.py            (full run, 50 seeds)
        python src/run_experiment.py --seeds 5  (quick check)
"""

import argparse
import json
import os
import time

import numpy as np

from market import (HEDGE_BOT, M, Q_BOT, consumer_surplus, deviation_test,
                    monopoly_price, nash_price, price_grid, profit,
                    profit_table, run_market)

# Learning settings (Calvano et al. 2020 baseline)
ALPHA = 0.15     # Q-learning step size
DELTA = 0.95     # how much bots value the future
BETA = 4e-6      # how fast random exploration fades
T_TRAIN = 3_000_000
T_EVAL = 10_000
# Hedge learning rate: the textbook no-regret choice for this horizon
ETA = float(np.sqrt(8 * np.log(M) / (T_TRAIN + T_EVAL)))

CONDITIONS = {
    # name: (bot types, can see past prices, forced random-price share)
    "baseline":      ([Q_BOT, Q_BOT], True, 0.0),
    "hide_prices":   ([Q_BOT, Q_BOT], False, 0.0),
    "random_5pct":   ([Q_BOT, Q_BOT], True, 0.05),
    "one_hedge_bot": ([Q_BOT, HEDGE_BOT], True, 0.0),
    "third_seller":  ([Q_BOT, Q_BOT, Q_BOT], True, 0.0),
}
# Extra: how much random pricing is needed? (dose sweep for one lever)
SWEEP = [0.0, 0.01, 0.02, 0.05, 0.10, 0.20]
# Extra: robustness checks for the Hedge result
ROBUST = {
    # name: (bot types, Hedge learning-rate multiplier)
    "hedge_eta_x0.1":        ([Q_BOT, HEDGE_BOT], 0.1),
    "hedge_eta_x10":         ([Q_BOT, HEDGE_BOT], 10.0),
    "three_sellers_1_hedge": ([Q_BOT, Q_BOT, HEDGE_BOT], 1.0),
    "two_hedge_bots":        ([HEDGE_BOT, HEDGE_BOT], 1.0),
}


def benchmarks(n):
    pn, pm = nash_price(n), monopoly_price(n)
    return {
        "p_nash": pn, "p_mono": pm,
        "pi_nash": profit(np.full(n, pn))[0], "pi_mono": profit(np.full(n, pm))[0],
        "cs_nash": consumer_surplus(np.full(n, pn)),
        "cs_mono": consumer_surplus(np.full(n, pm)),
    }


def one_run(seed, types, memory, eps_min, cache, eta=None):
    n = len(types)
    if n not in cache:
        grid = price_grid(n)
        table, cs_table = profit_table(n, grid)
        cache[n] = (grid, table, cs_table, benchmarks(n))
    grid, table, cs_table, b = cache[n]
    types_arr = np.array(types, dtype=np.int64)
    prof, act, cs, last_change, Q, s = run_market(
        seed, types_arr, memory, ALPHA, DELTA, BETA, eps_min, ETA if eta is None else eta,
        T_TRAIN, T_EVAL, table, cs_table)
    gain = (prof - b["pi_nash"]) / (b["pi_mono"] - b["pi_nash"])
    cs_index = (cs - b["cs_mono"]) / (b["cs_nash"] - b["cs_mono"])
    welfare = cs + prof.sum()
    welfare_nash = b["cs_nash"] + n * b["pi_nash"]
    out = {
        "seed": seed,
        "profit": prof.tolist(),
        "profit_gain": gain.tolist(),            # 0 = competitive, 1 = cartel
        "collusion_index": float(gain.mean()),
        "mean_price": float(np.interp(act, np.arange(M), grid).mean()),
        "consumer_index": float(cs_index),       # 1 = competitive, 0 = cartel
        "welfare_vs_competitive": float(welfare / welfare_nash),
        "last_plan_change": int(last_change),
        "stable_last_500k": bool(last_change < T_TRAIN - 500_000),
    }
    if n == 2 and memory and all(t == Q_BOT for t in types):
        dev = deviation_test(Q, s, grid, table)
        out["punished_cheat"] = None if dev is None else bool(dev["punished"])
        if dev is not None:
            out["rival_path_after_cheat"] = [float(x) for x in dev["rival_path"]]
            out["rival_price_before_cheat"] = float(dev["rival_price_before"])
    return out


def mean_ci(x):
    x = np.asarray(x, dtype=float)
    return float(x.mean()), float(1.96 * x.std(ddof=1) / np.sqrt(len(x)))


def perm_test(a, b, reps=20_000, rng=np.random.default_rng(0)):
    """Two-sided permutation test on the difference of means."""
    a, b = np.asarray(a), np.asarray(b)
    obs = abs(a.mean() - b.mean())
    pooled = np.concatenate([a, b])
    hits = 0
    for _ in range(reps):
        rng.shuffle(pooled)
        hits += abs(pooled[:len(a)].mean() - pooled[len(a):].mean()) >= obs
    return (hits + 1) / (reps + 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "results"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    cache = {}
    raw = {}
    t0 = time.time()
    for name, (types, memory, eps) in CONDITIONS.items():
        raw[name] = [one_run(s, types, memory, eps, cache) for s in range(args.seeds)]
        print(f"{name:14s} done ({time.time() - t0:.0f}s)")
    sweep = {}
    for eps in SWEEP:
        sweep[str(eps)] = [one_run(s, [Q_BOT, Q_BOT], True, eps, cache)
                           for s in range(args.seeds)]
        print(f"sweep eps={eps} done ({time.time() - t0:.0f}s)")

    robust = {}
    for name, (types, mult) in ROBUST.items():
        robust[name] = [one_run(s, types, True, 0.0, cache, eta=ETA * mult)
                        for s in range(args.seeds)]
        print(f"robust {name} done ({time.time() - t0:.0f}s)")

    # Summary
    base = [r["collusion_index"] for r in raw["baseline"]]
    rows = []
    for name, runs in raw.items():
        ci = [r["collusion_index"] for r in runs]
        row = {"condition": name, "n_seeds": len(runs)}
        row["collusion_index"] = mean_ci(ci)
        row["mean_price"] = mean_ci([r["mean_price"] for r in runs])
        row["consumer_index"] = mean_ci([r["consumer_index"] for r in runs])
        row["welfare_vs_competitive"] = mean_ci([r["welfare_vs_competitive"] for r in runs])
        row["share_runs_index_above_0.5"] = float(np.mean([c > 0.5 for c in ci]))
        row["stable_share"] = float(np.mean([r["stable_last_500k"] for r in runs]))
        row["p_vs_baseline"] = None if name == "baseline" else perm_test(ci, base)
        if name == "one_hedge_bot":
            row["q_bot_profit_gain"] = mean_ci([r["profit_gain"][0] for r in runs])
            row["hedge_bot_profit_gain"] = mean_ci([r["profit_gain"][1] for r in runs])
        pun = [r.get("punished_cheat") for r in runs if r.get("punished_cheat") is not None]
        if pun:
            row["share_punish_cheat"] = float(np.mean(pun))
            row["n_cheat_tests"] = len(pun)
        rows.append(row)
    sweep_rows = []
    for eps, runs in sweep.items():
        sweep_rows.append({
            "random_share": float(eps),
            "collusion_index": mean_ci([r["collusion_index"] for r in runs]),
            "consumer_index": mean_ci([r["consumer_index"] for r in runs]),
            "welfare_vs_competitive": mean_ci([r["welfare_vs_competitive"] for r in runs]),
        })
    robust_rows = []
    for name, runs in robust.items():
        row = {"check": name,
               "collusion_index": mean_ci([r["collusion_index"] for r in runs]),
               "consumer_index": mean_ci([r["consumer_index"] for r in runs]),
               "profit_gain_by_seller": [mean_ci([r["profit_gain"][i] for r in runs])
                                         for i in range(len(runs[0]["profit_gain"]))]}
        robust_rows.append(row)
    settings = {"alpha": ALPHA, "delta": DELTA, "beta": BETA, "T_train": T_TRAIN,
                "T_eval": T_EVAL, "eta_hedge": ETA, "price_grid_size": M,
                "benchmarks": {n: v[3] for n, v in cache.items()}}
    with open(os.path.join(args.out, "raw_results.json"), "w") as f:
        json.dump({"settings": settings, "conditions": raw, "sweep": sweep, "robustness": robust}, f, indent=1, default=float)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({"settings": settings, "summary": rows, "sweep": sweep_rows, "robustness": robust_rows}, f, indent=1, default=float)
    print(json.dumps(rows, indent=1, default=float))
    print(json.dumps(sweep_rows, indent=1, default=float))
    print(json.dumps(robust_rows, indent=1, default=float))


if __name__ == "__main__":
    main()
