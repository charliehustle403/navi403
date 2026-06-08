# Role concept: Z:S:MM_FIORI_BUYER (single)

Business task: Fiori app access for a purchasing buyer.

Frontend: Fiori catalog SAP_MM_BC_BUYER assigned (tiles for "Manage Purchase Orders").
Backend: NO S_SERVICE authorizations for the corresponding OData services were added;
the underlying backend transactions/objects (ME21N etc.) are also not in the role.

Concern: frontend catalog granted but backend authorization (S_SERVICE / OData + backend
objects) not aligned. Assess Fiori/S4 frontend-backend alignment.
