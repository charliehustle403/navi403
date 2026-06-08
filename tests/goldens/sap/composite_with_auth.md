# Role concept: Z:C:FI_POWER (composite)

Business task: bundle for senior finance users.

Composite role Z:C:FI_POWER:
- bundles singles Z:S:FI_AP_DISPLAY and Z:S:FI_AR_DISPLAY
- ALSO carries its own authorization data directly: S_TCODE (FB50, FB60) and
  F_BKPF_BUK maintained on the composite itself.

Question: is it sound for a composite to carry authorizations in addition to bundling
singles? Reviewer should assess the architecture.
