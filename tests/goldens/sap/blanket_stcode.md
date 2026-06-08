# Role concept: Z_FI_AP_CLERK (single)

Business task: Accounts Payable clerk — enter and display vendor invoices.

Authorizations (proposed):
- S_TCODE: TCD = * (all transaction codes)
- F_BKPF_BUK: ACTVT = 01, 02, 03; BUKRS = *
- M_RECH_WRK: ACTVT = *; WERKS = *

Notes: built manually in PFCG, not from SU24 proposals. Single role, no derived layer.
Company codes in scope: 1000, 2000 (Germany), but BUKRS left as *.
