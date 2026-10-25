"""A simple repeated pricing market with learning pricing bots.

The market follows Calvano et al. (2020, AER): each seller picks a price from a
grid every round, buyers choose with logit demand, and sellers earn
(price - cost) * share. Bots are either Q-learners (they can learn to collude)
or Hedge bots (a no-regret algorithm, see Collina et al. 2025).
"""

import numpy as np
from numba import njit

# Market settings from Calvano et al. (2020), baseline case.
A = 2.0      # product quality
A0 = 0.0     # value of buying nothing
MU = 0.25    # how much buyers care about price differences
COST = 1.0   # marginal cost
M = 15       # number of prices on the grid
XI = 0.1     # how far the grid reaches past the competitive and monopoly price

Q_BOT = 0
HEDGE_BOT = 1


def demand(p):
    e = np.exp((A - np.asarray(p, dtype=float)) / MU)
    return e / (e.sum() + np.exp(A0 / MU))


def profit(p):
    p = np.asarray(p, dtype=float)
    return (p - COST) * demand(p)


def consumer_surplus(p):
    p = np.asarray(p, dtype=float)
    return MU * np.log(np.exp((A - p) / MU).sum() + np.exp(A0 / MU))


def nash_price(n):
    """Competitive (one-shot Nash) price for n identical sellers."""
    p = COST + MU
    for _ in range(10_000):
        q = demand(np.full(n, p))[0]
        p = COST + MU / (1 - q)
    return p


def monopoly_price(n):
    """Price that maximises the sellers' joint profit (full cartel)."""
    grid = np.linspace(COST, COST + 3, 300_001)
    e = np.exp((A - grid) / MU)
    q = e / (n * e + np.exp(A0 / MU))
    return grid[np.argmax((grid - COST) * q)]


def price_grid(n):
    pn, pm = nash_price(n), monopoly_price(n)
    return np.linspace(pn - XI * (pm - pn), pm + XI * (pm - pn), M)


def profit_table(n, grid):
    """Profit of every seller for every combination of grid prices.

    Row index encodes the price combination: idx = sum a_i * M**(n-1-i).
    """
    rows = M ** n
    table = np.zeros((rows, n))
    cs = np.zeros(rows)
    for idx in range(rows):
        a = np.unravel_index(idx, (M,) * n)
        p = grid[list(a)]
        table[idx] = profit(p)
        cs[idx] = consumer_surplus(p)
    return table, cs


@njit(cache=True)
def _encode(acts, n, m):
    idx = 0
    for i in range(n):
        idx = idx * m + acts[i]
    return idx


@njit(cache=True)
def run_market(seed, types, memory, alpha, delta, beta, eps_min, eta,
               T, T_eval, table, cs_table):
    """Train the bots for T rounds, then watch them for T_eval rounds.

    types   : array with Q_BOT or HEDGE_BOT for each seller
    memory  : if False, Q-learners cannot see past prices (one fixed state)
    eps_min : floor on random exploration (forced random pricing)
    eta     : Hedge learning rate
    Returns mean profit per seller, mean price index per seller and mean
    consumer surplus during evaluation, the round when any Q-bot last changed its greedy plan,
    the Q-tables, and the last state.
    """
    np.random.seed(seed)
    n = types.shape[0]
    m = M
    S = m ** n if memory else 1
    Q = np.zeros((n, S, m))
    # Start Q-values at the payoff from facing random rivals forever.
    for i in range(n):
        for a in range(m):
            tot = 0.0
            cnt = 0
            for idx in range(m ** n):
                # own action of seller i inside idx
                ai = (idx // (m ** (n - 1 - i))) % m
                if ai == a:
                    tot += table[idx, i]
                    cnt += 1
            v = tot / cnt / (1.0 - delta)
            for s in range(S):
                Q[i, s, a] = v
    logw = np.zeros((n, m))
    acts = np.zeros(n, dtype=np.int64)
    s = np.random.randint(S)
    last_change = 0

    sum_profit = np.zeros(n)
    sum_act = np.zeros(n)
    sum_cs = 0.0
    total = T + T_eval
    for t in range(total):
        evaluating = t >= T
        if evaluating:
            eps = eps_min
        else:
            eps = max(np.exp(-beta * t), eps_min)
        # 1) every seller picks a price
        for i in range(n):
            if types[i] == 0:
                if np.random.random() < eps:
                    acts[i] = np.random.randint(m)
                else:
                    acts[i] = np.argmax(Q[i, s])
            else:
                w = np.exp(logw[i] - logw[i].max())
                w = w / w.sum()
                r = np.random.random()
                c = 0.0
                k = m - 1
                for j in range(m):
                    c += w[j]
                    if r < c:
                        k = j
                        break
                acts[i] = k
        idx = _encode(acts, n, m)
        s_new = idx if memory else 0
        # 2) learning
        for i in range(n):
            if types[i] == 0:
                if not evaluating:
                    old_best = np.argmax(Q[i, s])
                    target = table[idx, i] + delta * Q[i, s_new].max()
                    Q[i, s, acts[i]] = (1 - alpha) * Q[i, s, acts[i]] + alpha * target
                    if np.argmax(Q[i, s]) != old_best:
                        last_change = t
            else:
                # full-information Hedge: credit every price it could have used
                base = idx - acts[i] * m ** (n - 1 - i)
                for k in range(m):
                    logw[i, k] += eta * table[base + k * m ** (n - 1 - i), i]
        if evaluating:
            sum_cs += cs_table[idx]
            for i in range(n):
                sum_profit[i] += table[idx, i]
                sum_act[i] += acts[i]
        s = s_new
    return sum_profit / T_eval, sum_act / T_eval, sum_cs / T_eval, last_change, Q, s


def deviation_test(Q, s, grid, table, steps=15):
    """Cheat test from Calvano et al.: seller 0 secretly undercuts once.

    Both bots play their learned greedy plans. In one round, seller 0 is forced
    to play its best one-round price against seller 1. We record seller 1's
    price before and after. A drop right after the cheat is a 'punishment'.
    Works for two Q-bots with memory.
    """
    m = len(grid)
    # let the play settle first
    for _ in range(50):
        a = [int(np.argmax(Q[0, s])), int(np.argmax(Q[1, s]))]
        s = a[0] * m + a[1]
    a1_before = int(np.argmax(Q[1, s]))
    a0_normal = int(np.argmax(Q[0, s]))
    # seller 0's best one-round reply to seller 1's current price
    best = int(np.argmax([table[k * m + a1_before, 0] for k in range(m)]))
    if best == a0_normal:
        return None  # nothing to cheat with: already best-responding
    s = best * m + a1_before
    path = []
    for _ in range(steps):
        a = [int(np.argmax(Q[0, s])), int(np.argmax(Q[1, s]))]
        path.append(grid[a[1]])
        s = a[0] * m + a[1]
    return {
        "rival_price_before": grid[a1_before],
        "rival_price_after": path[0],
        "punished": path[0] < grid[a1_before] - 1e-9,
        "rival_path": path,
    }
