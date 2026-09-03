# Case 3b - return book: annual rebalancing + 90/10 profit sharing

_RSP asset side only, projected to year 50; benefit outflows are paid from the LMP and are not shown here._

Year-end rebalancing to Aggressive_Diversified (1x / year). **Profit sharing only from year 15** (when benefits begin): years 1-14 the whole return compounds in the book, un-shared; from year 15 on, 90% of each year's investment profit is paid to policyholders (equal EUR sold from every sleeve), 10% retained. Deterministic per-sleeve annual returns from the weekly history.

| | EUR bn |
|---|--:|
| contributions paid in (10 x 0.5) | 5.00 |
| **return-book MV, end of accumulation (yr 10, pre-sharing)** | **8.39** |
| return-book MV, end of projection (yr 50) | 18.96 |
| cumulative policyholder profit share (yr 15+) | 55.82 |
| cumulative insurer retained (10%) | 6.20 |
| naive fully-reinvested book, no sharing ever | 557.88 |

No profit share is taken before benefits begin, so the whole accumulation return compounds: the deployed return book is the **yr-10 pre-sharing MV (EUR 8.39bn)** - `case3_model` uses this when `return_book_mode='projected'`.  From year 15 the 90% is a pass-through: it leaves the book (equal EUR sold from each sleeve) and is credited to policyholders, so it does not sit on the insurer's asset side; only the retained 10% keeps compounding.  Losses in the payout phase carry forward and net against future profit before any share is paid.
