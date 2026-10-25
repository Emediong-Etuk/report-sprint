"""Make the report figures from results/summary.json and results/raw_results.json."""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(__file__)
RES = os.path.join(HERE, "..", "results")
FIG = os.path.join(HERE, "..", "figures")
os.makedirs(FIG, exist_ok=True)

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#a3a29c"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e0"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
})

LABELS = {
    "baseline": "No restriction\n(2 learning bots)",
    "hide_prices": "Hide rival prices",
    "random_5pct": "Force 5% random prices",
    "third_seller": "Add a third seller",
    "one_hedge_bot": "Swap ONE bot for a\nno-regret (Hedge) bot",
}

summary = json.load(open(os.path.join(RES, "summary.json")))
raw = json.load(open(os.path.join(RES, "raw_results.json")))

# Figure 1: collusion index per condition, with every seed as a dot
order = ["baseline", "hide_prices", "third_seller", "random_5pct", "one_hedge_bot"]
rows = {r["condition"]: r for r in summary["summary"]}
fig, ax = plt.subplots(figsize=(7, 3.6))
for y, name in enumerate(order[::-1]):
    mean, ci = rows[name]["collusion_index"]
    color = BLUE if name == "one_hedge_bot" else (ORANGE if name == "baseline" else GRAY)
    ax.barh(y, mean, height=0.55, color=color, zorder=2)
    ax.errorbar(mean, y, xerr=ci, color=INK, capsize=3, lw=1, zorder=3)
    pts = [r["collusion_index"] for r in raw["conditions"][name]]
    jitter = (np.random.default_rng(y).random(len(pts)) - 0.5) * 0.3
    ax.scatter(pts, y + jitter, s=8, color=INK, alpha=0.35, zorder=4, lw=0)
    ax.text(max(mean + ci, max(pts)) + 0.03, y, f"{mean:.2f}", va="center", color=INK, fontsize=9)
ax.set_yticks(range(len(order)))
ax.set_yticklabels([LABELS[n] for n in order[::-1]])
ax.axvline(0, color=INK2, lw=1)
ax.axvline(1, color=INK2, lw=1, ls=":")
ax.text(0.01, len(order) - 0.45, "fair competition", color=INK2, fontsize=8)
ax.text(0.99, len(order) - 0.45, "full cartel", color=INK2, fontsize=8, ha="right")
ax.set_xlabel("Collusion index (0 = fair competition, 1 = full cartel)")
ax.set_xlim(-0.35, 1.35)
ax.grid(axis="x", color=GRID, zorder=0)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig1_collusion_by_restriction.png"), dpi=200)

# Figure 2: how much forced randomness is needed
sw = summary["sweep"]
x = [100 * r["random_share"] for r in sw]
fig, ax = plt.subplots(figsize=(6, 3.2))
for key, color, label in [("collusion_index", ORANGE, "Collusion index"),
                          ("consumer_index", BLUE, "Shopper welfare index")]:
    m = np.array([r[key][0] for r in sw])
    c = np.array([r[key][1] for r in sw])
    ax.fill_between(x, m - c, m + c, color=color, alpha=0.15, lw=0)
    ax.plot(x, m, color=color, lw=2, marker="o", ms=5)
    ax.text(x[-1] + 0.6, m[-1], label, color=INK, va="center", fontsize=9)
hedge = rows["one_hedge_bot"]["collusion_index"][0]
ax.axhline(hedge, color=GRAY, lw=1, ls="--")
ax.text(0.3, hedge + 0.03, f"one Hedge bot, no randomness: collusion {hedge:.2f}", color=INK2, fontsize=8)
ax.set_xlabel("Share of rounds where each bot must pick a random price (%)")
ax.set_ylim(-0.05, 1.05)
ax.set_xlim(-0.5, 32)
ax.grid(axis="y", color=GRID)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig2_random_price_dose.png"), dpi=200)

# Figure 3: cheat test (positive control) - mean rival price after a one-round cheat
paths, before = [], []
for r in raw["conditions"]["baseline"]:
    if r.get("rival_path_after_cheat"):
        paths.append(r["rival_path_after_cheat"])
        before.append(r["rival_price_before_cheat"])
paths = np.array(paths)
b = summary["settings"]["benchmarks"]["2"]
fig, ax = plt.subplots(figsize=(6, 3.2))
steps = np.arange(0, paths.shape[1] + 1)
mean_path = np.concatenate([[np.mean(before)], paths.mean(0)])
for p, b0 in zip(paths, before):
    ax.plot(steps, np.concatenate([[b0], p]), color=GRAY, lw=0.6, alpha=0.4)
ax.plot(steps, mean_path, color=ORANGE, lw=2, marker="o", ms=4, label="average over runs")
ax.axhline(b["p_nash"], color=INK2, lw=1, ls="--")
ax.axhline(b["p_mono"], color=INK2, lw=1, ls=":")
ax.text(steps[-1], b["p_nash"] - 0.035, "fair-competition price", ha="right", color=INK2, fontsize=8)
ax.text(steps[-1], b["p_mono"] + 0.015, "cartel price", ha="right", color=INK2, fontsize=8)
ax.annotate("Bot A cheats here", xy=(0.5, mean_path[0]), xytext=(1.6, 1.97),
            arrowprops=dict(arrowstyle="->", color=INK2), color=INK, fontsize=8)
ax.set_xlabel("Rounds after the cheat (0 = before)")
ax.set_ylabel("Bot B's price")
ax.grid(axis="y", color=GRID)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "fig3_cheat_test.png"), dpi=200)
print("figures saved to", os.path.abspath(FIG))
