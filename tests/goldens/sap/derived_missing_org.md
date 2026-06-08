# Role concept: Z_SD_ORDER_PROC (master + derived)

Business task: Sales order processing for two sales orgs.

Master role Z:M:SD_ORDER_PROC holds the transactions and field values via SU24.
Derived roles:
- Z:D:SD_ORDER_PROC_1000 — intended for sales org 1000
- Z:D:SD_ORDER_PROC_2000 — intended for sales org 2000

Issue to assess: the org-level values (VKORG, VTWEG, SPART) were maintained in the
MASTER role and the derived roles inherited identical org values; the derived layer was
not used to differentiate sales org. So both derived roles currently grant VKORG = 1000
and 2000 both.
