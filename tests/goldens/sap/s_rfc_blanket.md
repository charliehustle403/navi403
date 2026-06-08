# Role concept: Z:S:INTERFACE_USER (single, technical)

Business task: technical/interface user for an inbound integration.

Authorizations:
- S_RFC: RFC_TYPE = FUGR; RFC_NAME = *; ACTVT = 16
- S_TCODE: SM59 (display)

Concern: blanket S_RFC with RFC_NAME = * grants execute on every function group. Assess
auth-object hygiene (sensitive object with no justification) and least privilege.
