# Role concept: Z:S:FI_REPORT_USER (single, PRODUCTION)

Business task: run finance reports in the production system.

Authorizations:
- S_TCODE: a list of FI report transactions (FBL3N, S_ALR_*)
- S_DEVELOP: ACTVT = 01,02,03,16; OBJTYPE = * (granted "for ad-hoc query building")

Concern: S_DEVELOP in production on a reporting role. Assess auth-object hygiene and
least privilege.
