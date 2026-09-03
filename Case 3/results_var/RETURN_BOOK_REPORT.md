# Case 3b - return book: semi-annual rebalancing + 90/10 profit sharing

2x / year rebalancing to Aggressive_Diversified; 90% of each half-year investment profit paid to policyholders (funded by selling an equal EUR amount from every sleeve), 10% retained and left invested. Deterministic per-sleeve half-year returns from the weekly history.

| | EUR bn |
|---|--:|
| contributions paid in (10 x 0.5) | 5.00 |
| **return-book MV, end of accumulation** | **5.26** |
| cumulative policyholder profit share | 2.36 |
| cumulative insurer retained (10%) | 0.26 |
| naive fully-reinvested book (no profit share) | 8.58 |

The 90% profit-share leakage is why the deployed return book is close to the contributions paid in rather than a fully-compounded figure - `case3_model` uses this MV as the return-book size when `return_book_mode='projected'`.

The policyholder 90% is a pass-through: it leaves the return book (equal EUR sold from each sleeve) and is credited to policyholders, so it does not sit on the insurer's asset side. Only the retained 10% compounds in the book. Losses are carried forward and net against future profit before any share is paid.
