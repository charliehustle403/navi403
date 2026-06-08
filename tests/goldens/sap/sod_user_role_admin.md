# Role concept: Z:S:BASIS_SECADMIN (single)

Business task: "security administrator — manage users and roles."

Authorizations:
- S_USER_GRP: ACTVT = 01,02,03,06; CLASS = *
- S_USER_AGR: ACTVT = 01,02,03,64; ACT_GROUP = Z:*
- S_TCODE: SU01, PFCG

Concern: this single role lets one person both create/maintain users (SU01) AND
create/maintain roles (PFCG) — maker and checker in one role. Assess SoD.
