# Case 3b - Solvency II ratio and MCR

**Own Funds** (basic own funds ~ economic surplus = market-value assets - best-estimate
liability PV; risk margin and EPIFP not modelled separately - see caveat).

**SCR** = 1-year **99.5%** VaR of own funds, from `case3_model` Historical Simulation
(`run_hs(Config(confidence=0.995, ...))`).

**MCR** = 25 % of SCR - the Solvency II Art. 129 corridor is 25 %-45 % of SCR; the
linear MCR for a life book of this profile falls below 25 % of SCR, so the floor binds.

| deployment / overlay | Own Funds | SCR (99.5% 1y) | **SII ratio** | MCR | **MCR ratio** |
|---|--:|--:|--:|--:|--:|
| full deployment, no overlay | EUR 3.19bn | EUR 1.24bn | **257 %** | EUR 0.31bn | 1,030 % |
| full deployment, **+ receiver-IRS overlay** | EUR 3.19bn | EUR 0.94bn | **340 %** | EUR 0.23bn | 1,360 % |
| projected return book (EUR 13.4bn assets), no overlay | EUR 6.58bn | EUR 1.66bn | **395 %** | EUR 0.42bn | 1,580 % |

- Headline (recommended strategy = with the receiver-IRS overlay): **SII ratio ~ 340 %**,
  **MCR EUR ~0.23bn (MCR ratio ~1,360 %)**.
- Mean across the three views: SII ratio **~330 %**.
- All comfortably above the 100 % regulatory pass; the binding board constraint remains
  the internal 1.20 funding-ratio floor, not the SCR.

## Caveats

- SII own funds would deduct a **risk margin** (~6 % CoC on run-off SCR, order
  EUR 0.2-0.4bn here) and add **expected profit in future premiums**; netting these
  leaves the ratio in a ~250-340 % band.
- **MCR** uses the 25 %-of-SCR regulatory floor (the standard simplification and the
  usual binding constraint for a life book); a full linear-formula MCR needs
  factor x technical provisions + factor x capital-at-risk inputs not in this model.
- SCR here is the internal-model surplus VaR, not the Standard Formula.

Source: `results_var/HS_REPORT_scr_*.md`.
