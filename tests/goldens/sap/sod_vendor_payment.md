# Role concept: Z:C:AP_FULL (composite)

Business task: "one role to run accounts payable end to end."

Composite Z:C:AP_FULL bundles these singles:
- Z:S:AP_VENDOR_CREATE — create/maintain vendor master (XK01/XK02), incl. bank details
- Z:S:AP_INVOICE_POST  — post vendor invoices (FB60)
- Z:S:AP_PAYMENT_RUN   — run the automatic payment program (F110)

All three are assigned to the same users via the composite. Assess for segregation of
duties across the bundled singles.
