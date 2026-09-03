"""
return_book.py
==============

Annual (end-of-year) dynamics of the Case 3b **return portfolio** (14 indices,
"Aggressive Diversified" weights), with the policyholder profit-sharing rule.

At each year end:
  1. each sleeve grows by its return over the year
  2. the contribution tranche arrives (EUR 0.5bn / yr, for the first
     `contribution_years` years) and is invested at the target weights
  3. **profit sharing - only from `profit_share_start_year` (year 15, when
     benefits begin)**.  In the accumulation + bridge years (1-14) the whole
     investment return compounds in the book, un-shared.  From year 15 on, if
     the book made an investment profit over the year (return-driven change in
     MV, contributions excluded, with a loss carry-forward), **90 %** is paid
     out to policyholders and **10 %** is retained by the insurer and left
     invested.  The 90 % payout is funded by **selling an equal EUR amount from
     each of the 14 sleeves** (capped at the sleeve's holding, shortfall
     redistributed).
  4. the remaining book is **rebalanced to the Aggressive Diversified target
     weights** (the annual "run the optimiser" step - weights come from
     `portfolio_optimization_final.xlsx`; a live run would re-optimise on data
     as of the rebalance date, hook: `weights_fn`).

Outputs
    project(...) -> DataFrame (one row per year): mv_total, contribution,
        pnl_year, payout_policyholder(+cum), retained_insurer(+cum),
        and per-sleeve MV.
    projected_book_mv(...) -> the return-book MV at the end of the accumulation
        phase (year `contribution_years`, before any profit sharing) - the
        number `case3_model` uses as the deployed return-book size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from case3_model import Config, load_index_history, load_return_weights

HERE = __import__("pathlib").Path(__file__).resolve().parent
OUT = HERE / "results_var"
EUR_BN = 1e9


@dataclass(frozen=True)
class RBConfig:
    contribution_per_year_eur: float = 0.5 * EUR_BN
    contribution_years: int = 10
    rebalance_per_year: int = 1                 # annual, at year end
    horizon_years: int = 50                     # accumulation (1-10) + bridge (11-14) + payout-phase sharing (15-50)
    profit_share_policyholder: float = 0.90     # requirement
    profit_share_start_year: float = 15.0       # no sharing before benefits begin
    weight_set: str = "Aggressive_Diversified"
    seed_mv_eur: float = 0.0                    # return book size at t=0


def period_returns_hist(weeks: int) -> pd.Series:
    """Deterministic per-sleeve simple return over `weeks` weeks, from the
    weekly history (compounded mean weekly log return)."""
    px = load_index_history()
    wlr = np.log(px).diff().dropna()
    return np.exp(weeks * wlr.mean()) - 1.0           # Series indexed by sleeve


def _sell_equal(mv: np.ndarray, amount: float) -> "tuple[np.ndarray, float]":
    """Raise `amount` by selling an equal EUR slice from every sleeve, capped at
    each holding; redistribute any shortfall across sleeves that still have
    room.  Returns (mv_after, cash_raised)."""
    n = len(mv)
    mv = mv.copy()
    raised = 0.0
    remaining = amount
    for _ in range(3):                                 # a few redistribution passes
        room = mv > 1e-6
        if remaining <= 1e-6 or not room.any():
            break
        per = remaining / room.sum()
        sell = np.where(room, np.minimum(per, mv), 0.0)
        mv -= sell
        raised += sell.sum()
        remaining = amount - raised
    return mv, raised


def project(rb: RBConfig | None = None,
            returns: np.ndarray | None = None,
            weights: pd.Series | None = None) -> pd.DataFrame:
    rb = rb or RBConfig()
    w = (load_return_weights(Config(return_weight_set=rb.weight_set))
         if weights is None else weights)
    sleeves = list(w.index)
    tw = w.to_numpy(dtype=float)
    tw = tw / tw.sum()
    n = len(sleeves)

    steps = rb.horizon_years * rb.rebalance_per_year
    dt = 1.0 / rb.rebalance_per_year
    if returns is None:
        r1 = period_returns_hist(round(52 / rb.rebalance_per_year)).reindex(sleeves).to_numpy()
        returns = np.tile(r1, (steps, 1))
    returns = np.asarray(returns, dtype=float)

    mv = rb.seed_mv_eur * tw
    contrib_per_step = rb.contribution_per_year_eur * dt
    carry = 0.0
    cum_pol = cum_ins = 0.0
    rows = []
    for s in range(steps):
        t = (s + 1) * dt
        before = mv.sum()
        mv = mv * (1.0 + returns[s])                       # 1. grow
        pnl = mv.sum() - before                            # investment P&L

        # 3. profit sharing - only once benefits begin (year 15+); before that
        #    the whole return compounds in the book, un-shared
        distributable = pnl + carry
        payout = retained = 0.0
        sharing = t >= rb.profit_share_start_year - 1e-9
        if sharing and distributable > 0.0:
            payout_target = rb.profit_share_policyholder * distributable
            mv, payout = _sell_equal(mv, payout_target)
            retained = distributable - payout             # 10% + unsold, stays invested
            carry = 0.0
        elif sharing:
            carry = distributable                         # negative, carried forward
        # (pre-year-15: no payout, no carry - the return is simply left in `mv`)
        cum_pol += payout
        cum_ins += retained

        # 2. contribution tranche (accumulation phase only)
        contribution = contrib_per_step if t <= rb.contribution_years + 1e-9 else 0.0
        mv = mv + contribution * tw

        # 4. rebalance to the Aggressive Diversified target weights
        mv = mv.sum() * tw

        rows.append({
            "t_years": t, "mv_total": mv.sum(), "contribution": contribution,
            "pnl_year": pnl, "loss_carry_forward": carry,
            "payout_policyholder": payout, "payout_policyholder_cum": cum_pol,
            "retained_insurer": retained, "retained_insurer_cum": cum_ins,
            **{f"mv[{sl}]": v for sl, v in zip(sleeves, mv)},
        })
    df = pd.DataFrame(rows).set_index("t_years")
    df.attrs["sleeves"] = sleeves
    return df


def projected_book_mv(rb: RBConfig | None = None, as_of_year: float | None = None,
                      **kw) -> float:
    """Return-book MV at the end of the accumulation phase (year
    `contribution_years` by default) - i.e. once all contributions are in but
    before profit sharing starts.  This is the deployed return-book size for the
    1-year VaR snapshot."""
    rb = rb or RBConfig()
    yr = float(rb.contribution_years if as_of_year is None else as_of_year)
    mv = project(rb, **kw)["mv_total"]
    hit = mv.index[np.isclose(mv.index.to_numpy(dtype=float), yr)]
    return float(mv.loc[hit[0]] if len(hit) else mv.iloc[-1])


# --------------------------------------------------------------------------- #
def _report_and_chart(df: pd.DataFrame, rb: RBConfig) -> None:
    OUT.mkdir(exist_ok=True)
    df.to_csv(OUT / "return_book_projection.csv")

    naive = rb.contribution_per_year_eur * rb.contribution_years
    y_acc = float(rb.contribution_years)
    acc_mv = df.loc[df.index == y_acc, "mv_total"]
    acc_mv = float(acc_mv.iloc[0]) if len(acc_mv) else float(df["mv_total"].iloc[-1])
    end_mv = df["mv_total"].iloc[-1]
    L = [
        "# Case 3b - return book: annual rebalancing + 90/10 profit sharing\n",
        f"_RSP asset side only, projected to year {int(df.index.max())}; benefit "
        f"outflows are paid from the LMP and are not shown here._\n",
        f"Year-end rebalancing to {rb.weight_set} ({rb.rebalance_per_year}x / "
        f"year). **Profit sharing only from year {rb.profit_share_start_year:.0f}** "
        f"(when benefits begin): years 1-{rb.profit_share_start_year-1:.0f} the "
        f"whole return compounds in the book, un-shared; from year "
        f"{rb.profit_share_start_year:.0f} on, 90% of each year's investment "
        f"profit is paid to policyholders (equal EUR sold from every sleeve), "
        f"10% retained. Deterministic per-sleeve annual returns from the weekly "
        f"history.\n",
        "| | EUR bn |", "|---|--:|",
        f"| contributions paid in (10 x 0.5) | {naive/1e9:.2f} |",
        f"| **return-book MV, end of accumulation (yr {rb.contribution_years}, pre-sharing)** | **{acc_mv/1e9:.2f}** |",
        f"| return-book MV, end of projection (yr {int(df.index.max())}) | {end_mv/1e9:.2f} |",
        f"| cumulative policyholder profit share (yr {rb.profit_share_start_year:.0f}+) | {df['payout_policyholder_cum'].iloc[-1]/1e9:.2f} |",
        f"| cumulative insurer retained (10%) | {df['retained_insurer_cum'].iloc[-1]/1e9:.2f} |",
        f"| naive fully-reinvested book, no sharing ever | {_naive_reinvest(rb)/1e9:.2f} |",
        "",
        "No profit share is taken before benefits begin, so the whole "
        "accumulation return compounds: the deployed return book is the "
        f"**yr-{rb.contribution_years} pre-sharing MV (EUR {acc_mv/1e9:.2f}bn)** - "
        "`case3_model` uses this when `return_book_mode='projected'`.  From year "
        f"{rb.profit_share_start_year:.0f} the 90% is a pass-through: it leaves "
        "the book (equal EUR sold from each sleeve) and is credited to "
        "policyholders, so it does not sit on the insurer's asset side; only the "
        "retained 10% keeps compounding.  Losses in the payout phase carry "
        "forward and net against future profit before any share is paid.",
    ]
    (OUT / "RETURN_BOOK_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C_MV, C_POL, C_INS, GRID = "#0072B2", "#D55E00", "#009E73", "#E6E6E6"
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.0))
    x = df.index.to_numpy()
    ax[0].plot(x, df["mv_total"] / 1e9, color=C_MV, lw=2.4, label="return-book MV")
    ax[0].plot(x, np.cumsum(df["contribution"]) / 1e9, color="#333", lw=1.4,
               ls=(0, (5, 3)), label="cumulative contributions")
    ax[0].axvline(rb.profit_share_start_year, color="#D55E00", lw=1.2, ls=":")
    ax[0].text(rb.profit_share_start_year + 0.2, ax[0].get_ylim()[1] * 0.1,
               "profit sharing\nstarts (yr 15)", fontsize=8, color="#D55E00")
    ax[0].set_title("Return-book MV vs contributions (EUR bn)")
    ax[0].set_xlabel("years"); ax[0].legend(frameon=False)
    ax[1].plot(x, df["payout_policyholder_cum"] / 1e9, color=C_POL, lw=2.4,
               label="policyholder profit share (90%)")
    ax[1].plot(x, df["retained_insurer_cum"] / 1e9, color=C_INS, lw=2.4,
               label="insurer retained (10%)")
    ax[1].set_title("Cumulative profit split (EUR bn)")
    ax[1].set_xlabel("years"); ax[1].legend(frameon=False)
    for a_ in ax:
        a_.grid(color=GRID, lw=0.7); a_.set_axisbelow(True)
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.suptitle("Case 3b - return book annual dynamics", fontsize=13,
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / "return_book_projection.png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote {OUT}/ : return_book_projection.csv, RETURN_BOOK_REPORT.md, "
          f"return_book_projection.png")


def _naive_reinvest(rb: RBConfig) -> float:
    """Same path, end of projection, with profit sharing switched off entirely -
    for the comparison line."""
    return projected_book_mv(RBConfig(**{**rb.__dict__, "profit_share_policyholder": 0.0}),
                             as_of_year=float(rb.horizon_years))


if __name__ == "__main__":
    rb = RBConfig()
    _report_and_chart(project(rb), rb)
