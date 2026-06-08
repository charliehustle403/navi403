# SAP S/4HANA role naming conventions

A consistent, parseable namespace makes a role landscape auditable at a glance.

- Use a fixed prefix per role type: `Z:S:` single, `Z:D:` derived, `Z:C:` composite.
- Derived roles must encode their master role so the lineage is inferable from the name alone.
- Encode the business scope (process area + org level) so reviewers can read intent without
  opening PFCG.
- Never reuse a name across environments; the namespace is part of the security model.

A name that does not tell you the role's type, master, and scope is a finding.
