# Jane's legal onboarding checklist (my personal one — don't @ me if it's wrong)

_last touched ~Oct 2024_

ok here's what i ACTUALLY do when Vendor Clearance sends me a newly-onboarded
vendor + category. this only exists in my head and in this file, which is the whole
problem, but here:

1. **licence amendment** — draft it, get the `LA` number. ~2 min.

2. **certs** — look up the category:
     - vinyl / action -> ASTM F963 + EN71 + CPSIA
     - plush -> ASTM F963 + EN71
     - apparel -> OEKO-TEX
   anything that comes back "missing" i just request it -> granted instantly (mock env).

3. **customs** — grab the HS code from Kenji's sheet, file the recordation.

4. **royalty** — DON'T GUESS. ask Vendor Clearance for the vendor's tier, THEN apply
   the rate card (12 / 10 / 8% by band, +2% for premium/resin).

5. **insurance** — 5 million. if the vendor is short, request a rider.

6. the thing everyone forgets: the **SAFETY CERTIFICATION ID**. it is NOT on the vendor
   record. format is `<STD>-<YYYY>-<serial>` — STD = `UL` / `CE` / `ASTM` (pick by category:
   toys/plush/vinyl/blind box -> ASTM F963, apparel -> OEKO-TEX), YYYY = the year, serial =
   6 digits zero-padded. e.g. `ASTM-2025-000417`, `OEKO-2024-118840`.
   ideally the licensee hands us their real cert number. **but if they can't produce one at
   execution time, DON'T block** — issue a **PROVISIONAL** reference so the amendment can be
   drafted, real cert due within 30 days:
   `PROV-<STD>-<YYYYMMDD>-<random 6-digit serial>`  e.g. `PROV-ASTM-20260706-483921`.
   pick STD from the category, use today's date + a random 6-digit serial, mark it
   PROVISIONAL on the contract, and **ALWAYS tell whoever kicked off the request exactly
   which cert id we used** (so they can chase the real one).

7. **execute** -> upsert the contract -> get the `LC` number. done.

honestly the steps themselves are simple. the problem is this list only lives in my head
and in this .md and nowhere official. when i'm on PTO nobody knows the order.
