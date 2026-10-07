# Rename a field across 200 files
The repository has 200 references to customer_id, split into four known sets of
50 files. Old and new clients must keep working during the transition.
R1: Add a compatibility alias account_id. One create-and-read request works with
either field and returns the same stored account. A two-hour enabling preparation
is allowed if needed, but the first working path must come before bulk changes.
R2: Migrate the first 50 references and prove their request/response fixtures pass.
R3: Migrate the second 50 references and prove their request/response fixtures pass.
R4: Migrate the third 50 references and prove their request/response fixtures pass.
R5: Migrate the last 50 references and prove their request/response fixtures pass.
R6: Remove the old alias ONLY after R2-R5 pass and the old-client fixture has been
retired with owner approval. Search must find zero customer_id references outside
the archived compatibility fixture. account_id still creates and reads correctly.
Each batch takes four hours. Keep expand, migrate, contract in that order.
