# Magic Number 100 in AvidaMT

All uses of `100` as a literal value in the codebase, grouped by purpose. Each entry includes what the constant likely represents and a confidence rating.

---

## Sampling / Recording Interval (every 100 updates)

Periodic statistics recording via `% 100 == 0` checks.

**Represents:** `recording_period` — the interval (in EA updates) between data-collection events.
**Confidence: High.** The config files explicitly have `recording.period=100`, and these in-code checks are doing the exact same thing: sampling every 100 updates. The in-code versions are just not reading from that config key and are instead hardcoded, which is the actual problem.

**Fixed:** All replaced with `get<RECORDING_PERIOD>(ea)` (or `get<RECORDING_PERIOD>(mea)` where the variable is named `mea`).

| File | Line | Before → After |
|------|------|----------------|
| `src/ts.h` | 95 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/mt_analysis.h` | 800 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/mt_propagule_orig.h` | 445 | `% 100` → `% get<RECORDING_PERIOD>(mea)` |
| `src/mt_propagule_orig.h` | 552 | `% 100` → `% get<RECORDING_PERIOD>(mea)` |
| `src/mt_propagule_orig.h` | 684 | `% 100` → `% get<RECORDING_PERIOD>(mea)` |
| `src/mt_propagule_orig.h` | 917 | `% 100` → `% get<RECORDING_PERIOD>(mea)` |
| `src/mt_propagule_orig.h` | 1053 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/gls.h` | 511 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/gls.h` | 749 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/lod_knockouts_fitness.h` | 666 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/lod_knockouts_fitness.h` | 912 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |
| `src/lod_knockouts_fitness.h` | 1129 | `% 100` → `% get<RECORDING_PERIOD>(ea)` |

---

## Genome / Representation Size (100 instructions)

Assertions and configuration enforcing a fixed genome size of 100.

**Represents:** `REPRESENTATION_SIZE` — the genome length in instructions.
**Confidence: High.** The comment literally says "Must use representation size of 100," and the ancestor code hardcodes specific instruction positions (e.g., `repr[24]`, `repr[25]`) that would be incorrect with a different genome length. The genome is resized to `get<REPRESENTATION_SIZE>(ea)` on the line just before the assert, so the assert is checking that the config value is exactly 100. The cfg files set `size=100` which confirms this is `REPRESENTATION_SIZE`.

**Fixed:** All six `assert(repr.size() == 100)` replaced with `assert(repr.size() == static_cast<size_t>(get<REPRESENTATION_SIZE>(ea)))`. Note: since `repr` was just sized by `get<REPRESENTATION_SIZE>(ea)`, the assert is now trivially true — the original guard against misconfiguring `REPRESENTATION_SIZE` to a non-100 value is no longer enforced at runtime. The cfg files are left as-is (they are data, not code).

| File | Lines | Before → After |
|------|-------|----------------|
| `src/multi_birth_selfrep_not_remote_ancestor.h` | 37–38 | `assert(repr.size() == 100)` → `assert(repr.size() == static_cast<size_t>(get<REPRESENTATION_SIZE>(ea)))` |
| `src/multi_birth_selfrep_not_remote_ancestor.h` | 84–85 | Same (second variant) |
| `src/multi_birth_selfrep_not_remote_ancestor.h` | 132–133 | Same (third variant) |
| `src/multi_birth_selfrep_not_remote_ancestor.h` | 191–192 | Same (fourth variant) |
| `src/multi_birth_selfrep_not_remote_ancestor.h` | 236–237 | Same (fifth variant) |
| `src/multi_birth_selfrep_not_remote_ancestor.h` | 281–282 | Same (sixth variant) |
| `etc/logic9.cfg` | 2 | `size=100` — unchanged (config file, not code) |
| `etc/major_transitions.cfg` | 2 | `size=100` — unchanged |
| `etc/ts_mt.cfg` | 2 | `size=100` — unchanged |

---

## Resource Initial Amount (100.0 units)

Starting resource levels for task-switching and related experiments.

**Represents:** `res_initial_amount` — the initial quantity of each resource pool at simulation start.
**Confidence: High.** The cfg files use the key `res_initial_amount = 100` for exactly this parameter. The in-code `make_resource("resX", 100.0, ...)` calls are hardcoding the same value rather than reading from config. The active code is in `ts.cpp`; the same lines are commented out in `gls.cpp`, `mt_lr_gls.cpp`, and `mt_lr_gls_dol_control.cpp`, suggesting those experiments switched to config-driven resource setup.

**Fixed:** All nine `100.0` values in `ts.cpp` replaced with `get<RES_INITIAL_AMOUNT>(ea)`. Added `#include <ea/digital_evolution/utils/task_switching.h>` to `ts.cpp` to expose that key (it was already available in the other cpp files via `gls.h`). The commented-out blocks in the other cpp files were left as-is. The cfg files are unchanged.

| File | Lines | Before → After |
|------|-------|----------------|
| `src/ts.cpp` | 82–90 | `make_resource("resX", 100.0, ...)` × 9 → `make_resource("resX", get<RES_INITIAL_AMOUNT>(ea), ...)` |
| `src/gls.cpp` | 109–117 | Commented out — unchanged |
| `src/mt_lr_gls.cpp` | 110–118 | Commented out — unchanged |
| `src/mt_lr_gls_dol_control.cpp` | 110–118 | Commented out — unchanged |
| `etc/major_transitions.cfg` | 43 | `res_initial_amount = 100` — unchanged (config file) |
| `etc/ts_mt.cfg` | 38 | `res_initial_amount = 100` — unchanged |

---

## Replicate Count (100 replicates per knockout)

Number of replicate simulation runs used in knockout analysis.

**Represents:** `lod_analysis_reps` — the number of independent replicate runs per knockout or phenotype analysis.
**Confidence: Moderate-High.** `ANALYSIS_LOD_REPS` is declared as a metadata key (`"ea.mt.lod_analysis_reps"`) in `lod_knockouts_fitness.h` — the hardcoded `int num_rep = 100` looks like it should be reading `get<ANALYSIS_LOD_REPS>(ea)` but never got wired up. The two sites (lines 1486 and 1611) are in different analysis functors but are clearly the same concept.

**Note:** Line 198 (`put<METAPOPULATION_SIZE>(100, metapop)`) is a *different* kind of 100. See below.

| File | Line | Code |
|------|------|------|
| `src/lod_knockouts_fitness.h` | 1486 | `int num_rep = 100;` — replicates per knockout |
| `src/lod_knockouts_fitness.h` | 1611 | `int num_rep = 100;` — replicates for phenotype analysis |

---

## Override Metapopulation Size (100 multicells)

Hardcoded population size used when setting up replicate metapopulations in knockout analysis.

**Represents:** `METAPOPULATION_SIZE` — the number of multicell groups in each replicate run.
**Confidence: Moderate.** The metadata key `METAPOPULATION_SIZE` exists and is used here directly, so the name is clear. What is uncertain is whether 100 is the right value or whether it should be read from the original EA's metadata rather than overridden. It may be intentionally overriding the experiment's configured value to force a standard analysis condition.

| File | Line | Code |
|------|------|------|
| `src/lod_knockouts_fitness.h` | 198 | `put<METAPOPULATION_SIZE>(100, metapop);` — overrides population size for each replicate run |

---

## Generational Difference Threshold (> 100)

Exit/revert conditions triggered when mean generational difference exceeds 100.

**Represents:** `max_gen_diff_threshold` — a heuristic ceiling on how far the mean generation can diverge before the replicate is considered pathological and abandoned.
**Confidence: Low-Moderate.** The value looks empirically chosen rather than derived — it is paired with another exit condition (`exit_mean_size > 5`), and together they act as sanity checks to short-circuit runaway replicates. There is no corresponding config key or named constant. The value 100 may have been chosen because it is much larger than typical mean-generation values in healthy runs, making it a conservative bail-out, but this is not documented anywhere.

| File | Line | Code |
|------|------|------|
| `src/lod_knockouts_fitness.h` | 716 | `if ((mean_gen_diff > 100))` — exit condition |
| `src/lod_knockouts_fitness.h` | 961 | `if (mean_gen_diff > 100)` — revert condition |
| `src/lod_knockouts_fitness.h` | 1178 | `if (mean_gen_diff > 100)` — reversion check |

---

## LOD Sampling Step (step by 100)

Level-of-descent counter incremented by 100 to subsample lineage ancestors.

**Represents:** `lod_sample_step` — how many ancestors to skip between analysis points when walking the line of descent.
**Confidence: Moderate.** The code walks the LOD and only stops every 100 depths to run the full knockout experiment, which would be too expensive at every ancestor. This is a performance/practicality tradeoff. The value feels like it was chosen to give a reasonable density of LOD coverage without being computationally prohibitive, but there is no config key for it and no comment explaining why 100 specifically.

| File | Line | Code |
|------|------|------|
| `src/lod_knockouts.h` | 300 | `next_lod += 100;` — step through lineage depth levels |
| `src/lod_knockouts_fitness.h` | 1077 | `next_lod += 100;` — same pattern in fitness knockouts |

---

## Sliding Window Size (keep 100 most recent replicates)

Limits history deques to 100 entries by popping the front when exceeded.

**Represents:** `history_window_size` — the number of recent replication events retained for running statistics.
**Confidence: Moderate.** The deque stores per-replicate germ statistics (counts, percentages, workloads) and is used to compute running means. Keeping only 100 entries bounds memory and focuses the window on recent history. The choice of 100 is consistent with the replicate-count theme elsewhere but has no named constant or config key.

| File | Line | Code |
|------|------|------|
| `src/gls.h` | 440 | `if (germ_num.size() > 100)` — cap germ-cell history |
| `src/gls.h` | 674 | `if (germ_num.size() > 100)` — cap replicate record history |

---

## Percentage Calculation (× 100)

Converting a fraction to a percentage by multiplying by 100.

**Represents:** The mathematical constant for percent conversion — not a domain magic number.
**Confidence: High.** This is standard arithmetic (`fraction * 100.0 = percent`). It is not a configurable parameter and should not be named. **Not changed** — this is correct as-is.

| File | Line | Code |
|------|------|------|
| `src/mt_propagule_orig.h` | 826 | `germ_count/((double) i->population().size())*100.0` — germ % of multicell |
| `src/gls.h` | 425 | `germ_count/((double) i->population().size())*100.0` — germ % of population |
| `src/gls.h` | 658 | `germ_count/((double) i->population().size())*100.0` — same, second functor |

---

## Config: Simulation Duration / Recording Period

Values set in `.cfg` files — these are data, not hardcoded logic, so they carry less risk than in-code literals.

| File | Line | Code | Represents | Confidence |
|------|------|------|------------|------------|
| `etc/logic9.cfg` | 21 | `updates=100` | Total simulation updates (`run_updates`) — very short run, likely a quick test config | High |
| `etc/major_transitions.cfg` | 37 | `recording.period=100` | `recording_period` — matches the in-code `% 100` checks | High |
| `etc/ts_mt.cfg` | 32 | `recording.period=100` | `recording_period` — same as above | High |
