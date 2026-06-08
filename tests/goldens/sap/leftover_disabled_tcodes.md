# Role concept: Z:S:SD_BILLING (single)

Business task: SD billing clerk — create and display billing documents.

Authorizations:
- S_TCODE: VF01, VF02, VF03 (billing) — current task
- S_TCODE also still contains: VA01, VA02 (sales order create/change), VK11 (pricing),
  and MIGO — left over from a previous copy-template; flagged "inactive / to remove".

Concern: transactions beyond the stated billing task remain in the role. Assess least
privilege and lifecycle (leftover/disabled tcodes).
