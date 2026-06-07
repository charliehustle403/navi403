# SAP segregation-of-duties (SoD): classic conflicts

Segregation of duties prevents one user from controlling an entire risky process. Flag these
classic conflicts, and check them across the singles bundled into a composite — a composite can
reintroduce a conflict that each single avoids on its own.

- Create vendor + post vendor payment.
- Maintain vendor bank details + run the payment proposal (F110).
- User administration + role administration (maker and checker in one role).
- Goods receipt + invoice verification for the same scope.

Authorization objects to watch when assessing SoD: `S_TCODE`, `F_BKPF_BUK`, `M_RECH_WRK`. Never
grant a blanket `*` on sensitive objects (`S_TCODE`, `S_TABU_DIS`, `S_DEVELOP`, `S_RFC`) without
explicit justification.
