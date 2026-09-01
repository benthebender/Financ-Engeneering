"""
main.py
=======

CLI for the callable-bond par-coupon engine. Takes a *grid* of structures, not a
single one.

Examples
--------
    # the case default: 7y NC2, 15 % vol, Hull-White
    python main.py

    # a grid: every (maturity, nc) pair
    python main.py --maturities 5 7 10 --nc 1 2 3 --vol 0.15 --engine hw

    # odd structures from a config file (list of CallableSpec dicts)
    python main.py --config spec.example.yaml

For every (maturity, nc) pair the tool prints:
  * the single-call ladder (par coupon for a one-off call at each candidate year)
  * the best single call
  * the Bermudan (all candidate years exercisable)
  * the spread of each over that maturity's bullet (= the par swap rate)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from curve_io import build_discount_curve, load_par_rates, max_curve_tenor
from pricer import CallableSpec, compare_structures, par_coupon
from scenarios import (
    DEFAULT_SCENARIOS,
    effective_risk,
    key_rate_dv01,
    scenario_analysis,
)

pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
pd.set_option("display.max_rows", 200)
pd.set_option("display.width", 160)


# --------------------------------------------------------------------------- #
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Par-coupon engine for callable bonds (single / Bermudan).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--maturities", type=int, nargs="+", default=[7],
                   help="bond maturities in years")
    p.add_argument("--nc", type=int, nargs="+", default=[2],
                   help="non-call periods in years (first callable year)")
    p.add_argument("--vol", type=float, default=0.15,
                   help="volatility (Black/lognormal by default, see --vol-type)")
    p.add_argument("--vol-type", choices=["black", "normal"], default="black",
                   help="'black' scales to a short-rate vol via sigma~=vol*r_ref; "
                        "'normal' feeds an absolute short-rate vol straight in")
    p.add_argument("--engine", choices=["hw", "black"], default="hw",
                   help="'hw' = Hull-White trinomial tree; 'black' = European "
                        "closed-form cross-check (single call only)")
    p.add_argument("--mean-reversion", type=float, default=0.03,
                   help="Hull-White mean reversion a")
    p.add_argument("--steps-per-year", type=int, default=12,
                   help="Hull-White tree steps per year")
    p.add_argument("--call-price", type=float, default=100.0,
                   help="redemption price on a call (per 100 face)")
    p.add_argument("--config", type=str, default=None,
                   help="YAML file: a list of CallableSpec dicts")
    p.add_argument("--curve-date", type=str, default=None,
                   help="curve date to load (default: latest fully-quoted date)")
    p.add_argument("--curve-file", type=str, default=None,
                   help="path to 'Swap curves.xlsx' (default: auto-find)")
    p.add_argument("--out", type=str, default=None,
                   help="directory to also write CSVs into")
    p.add_argument("--scenarios", action="store_true",
                   help="run the curve sensitivity / scenario analysis (issuer "
                        "P&L, call value, effective duration/convexity, key-rate "
                        "DV01) for the Bermudan of each (maturity, nc) pair")
    p.add_argument("--plots", action="store_true",
                   help="render presentation PNG charts of the sensitivity "
                        "analysis into --out (default ./charts)")
    p.add_argument("--struck-coupon", type=float, default=None,
                   help="issued coupon in bp for the scenario MTM (default: the "
                        "base-curve par coupon, i.e. struck at par today)")
    p.add_argument("--notional", type=float, default=100.0,
                   help="face amount for scenario money columns (default 100 = "
                        "report in points)")
    return p


def _engine_kw(args) -> dict:
    if args.engine == "hw":
        return {
            "mean_reversion": args.mean_reversion,
            "steps_per_year": args.steps_per_year,
            "vol_type": args.vol_type,
        }
    return {}


# --------------------------------------------------------------------------- #
def run_config(args, curve, out_dir) -> None:
    import yaml  # optional dependency, only needed here

    raw = yaml.safe_load(Path(args.config).read_text())
    if not isinstance(raw, list):
        raise SystemExit("--config file must contain a YAML list of spec dicts")
    specs = [CallableSpec(**d) for d in raw]

    print(f"# {len(specs)} structure(s) from {args.config}\n")
    df = compare_structures(curve, args.vol, specs, args.engine, **_engine_kw(args))
    print(df.to_string(index=False))
    if out_dir:
        path = out_dir / "compare_structures.csv"
        df.to_csv(path, index=False)
        print(f"\nwrote {path}")


def run_grid(args, curve, out_dir) -> None:
    max_tenor = max_curve_tenor(curve)
    ladders = []
    summary = []

    for m in args.maturities:
        if m > max_tenor:
            print(f"!! skipping maturity {m}y: exceeds curve ({max_tenor}y)\n")
            continue
        bullet_bp = None
        for nc in args.nc:
            if not (1 <= nc < m):
                print(f"!! skipping {m}y NC{nc}: need 1 <= nc < maturity\n")
                continue

            single = CallableSpec(m, nc, "single", call_price=args.call_price)
            res_s = par_coupon(curve, args.vol, single, args.engine, **_engine_kw(args))
            bullet_bp = res_s.bullet_par_coupon * 1e4

            print("=" * 68)
            print(f"  {m}y  NC{nc}   (candidates: "
                  f"{list(single.candidate_dates())})")
            print("=" * 68)
            print(res_s.summary())

            if args.engine == "black":
                print("  (black engine: Bermudan not available - single call only)\n")
                best_berm_bp = None
            else:
                berm = CallableSpec(m, nc, "bermudan", call_price=args.call_price)
                res_b = par_coupon(curve, args.vol, berm, args.engine, **_engine_kw(args))
                print(f"  bermudan par coupon : {res_b.par_coupon * 100:.4f} %"
                      f"   ({res_b.spread_bp:+.1f} bp vs bullet)\n")
                best_berm_bp = res_b.par_coupon * 1e4

            ld = res_s.call_ladder.reset_index()
            ld.insert(0, "maturity", m)
            ld.insert(1, "nc", nc)
            ladders.append(ld)
            summary.append({
                "maturity": m, "nc": nc,
                "bullet_bp": bullet_bp,
                "best_single_bp": res_s.par_coupon * 1e4,
                "best_single_year": res_s.best_call_year,
                "best_single_spread_bp": res_s.spread_bp,
                "bermudan_bp": best_berm_bp,
                "bermudan_spread_bp": (None if best_berm_bp is None
                                       else best_berm_bp - bullet_bp),
            })

    if summary:
        sdf = pd.DataFrame(summary)
        print("=" * 68)
        print("  SUMMARY  (all figures in basis points of coupon)")
        print("=" * 68)
        print(sdf.to_string(index=False))

    if out_dir and summary:
        ladf = pd.concat(ladders, ignore_index=True)
        ladf.to_csv(out_dir / "call_ladders.csv", index=False)
        pd.DataFrame(summary).to_csv(out_dir / "grid_summary.csv", index=False)
        print(f"\nwrote {out_dir / 'call_ladders.csv'} and "
              f"{out_dir / 'grid_summary.csv'}")


def run_scenarios(args, rates, out_dir) -> None:
    max_tenor = max_curve_tenor(build_discount_curve(rates))
    struck = None if args.struck_coupon is None else args.struck_coupon / 1e4

    for m in args.maturities:
        if m > max_tenor:
            print(f"!! skipping maturity {m}y: exceeds curve ({max_tenor}y)\n")
            continue
        for nc in args.nc:
            if not (1 <= nc < m):
                print(f"!! skipping {m}y NC{nc}: need 1 <= nc < maturity\n")
                continue

            spec = CallableSpec(m, nc, "bermudan", call_price=args.call_price)
            kw = _engine_kw(args)
            sc = scenario_analysis(rates, args.vol, spec, args.engine,
                                   scenarios=DEFAULT_SCENARIOS,
                                   notional=args.notional, struck_coupon=struck,
                                   **kw)
            er = effective_risk(rates, args.vol, spec, struck_coupon=struck,
                                engine=args.engine, notional=args.notional, **kw)
            kr = key_rate_dv01(rates, args.vol, spec, struck_coupon=struck,
                               engine=args.engine, notional=args.notional, **kw)

            print("=" * 78)
            print(f"  {m}y NC{nc} Bermudan   "
                  f"struck coupon {sc.attrs['struck_coupon_bp']:.1f} bp   "
                  f"notional {args.notional:,.0f}")
            print("=" * 78)
            fmt = lambda v: (f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}")
            print("Scenario table  (mtm & call_value in points; pnl columns in "
                  "money; issuer_pnl>0 = liability cheaper = gain)")
            print(sc.to_string(float_format=fmt))
            print("\nEffective duration / convexity (parallel +/-25bp):")
            print(er.to_string(float_format=fmt))
            print("\nKey-rate DV01  (money per +1bp at each node; +ve = issuer "
                  "gains as that node rises):")
            print(kr.to_string(float_format=fmt))
            print()

            if out_dir:
                tag = f"{m}y_nc{nc}"
                sc.to_csv(out_dir / f"scenarios_{tag}.csv")
                er.to_csv(out_dir / f"effrisk_{tag}.csv")
                kr.to_csv(out_dir / f"keyrate_{tag}.csv")
                print(f"wrote scenarios_{tag}.csv, effrisk_{tag}.csv, "
                      f"keyrate_{tag}.csv\n")


def run_plots(args, rates, out_dir) -> None:
    from plots import save_all

    out_dir = out_dir or Path("charts")
    struck = None if args.struck_coupon is None else args.struck_coupon / 1e4
    max_tenor = max_curve_tenor(build_discount_curve(rates))

    for m in args.maturities:
        if m > max_tenor:
            print(f"!! skipping maturity {m}y: exceeds curve ({max_tenor}y)\n")
            continue
        for nc in args.nc:
            if not (1 <= nc < m):
                print(f"!! skipping {m}y NC{nc}: need 1 <= nc < maturity\n")
                continue
            spec = CallableSpec(m, nc, "bermudan", call_price=args.call_price)
            written = save_all(rates, args.vol, spec, out_dir,
                               engine=args.engine, notional=args.notional,
                               struck_coupon=struck, **_engine_kw(args))
            print(f"{m}y NC{nc}: wrote {len(written)} files to {out_dir}/")
            for p in written:
                print(f"  {p.name}")


def main(argv=None) -> None:
    args = _parser().parse_args(argv)

    rates = load_par_rates(args.curve_file, date=args.curve_date)
    curve = build_discount_curve(rates)
    print(f"curve source : {rates.attrs.get('workbook', '?')}")
    print(f"curve date   : {rates.attrs.get('curve_date', '?')}  "
          f"({len(rates)} tenors {rates.index[0]}..{rates.index[-1]}, "
          f"max {max_curve_tenor(curve)}y)")
    print(f"rates (%)    : "
          + ", ".join(f"{t}={v:.3f}" for t, v in rates.items()))
    print(f"model        : {args.engine} engine, vol={args.vol} "
          f"({args.vol_type}), a={args.mean_reversion}, "
          f"{args.steps_per_year} steps/yr\n")

    out_dir = Path(args.out) if args.out else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    if args.plots:
        run_plots(args, rates, out_dir)
    elif args.scenarios:
        run_scenarios(args, rates, out_dir)
    elif args.config:
        run_config(args, curve, out_dir)
    else:
        run_grid(args, curve, out_dir)


if __name__ == "__main__":
    main()
