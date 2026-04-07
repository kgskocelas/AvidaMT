# AvidaMT Bug Report

Generated: 2026-04-04
Analyzer: Claude (cross-referenced AvidaMT src against ealib-modern)

---

## Severity Key

| Level | Meaning |
|-------|---------|
| **Critical** | Crash, undefined behavior, or data corruption |
| **High** | Won't compile, or produces wrong results silently |
| **Medium** | Wrong behavior in specific conditions |
| **Low** | Code quality, latent issues, minor confusion |

## Confidence Key

| Level | Meaning |
|-------|---------|
| **High** | Root cause is clear; fix is straightforward |
| **Medium** | Root cause is likely; fix may need verification |
| **Low** | Suspected issue; needs runtime confirmation |

---

## Bug 1 — Unsigned Underflow in `configurable_indel`

| Field | Value |
|-------|-------|
| **File** | `src/gls.h`, lines 80–90 |
| **Severity** | Critical |
| **Confidence** | High |
| **Active in** | `gls.cpp` → `gls` executable |

### What the Bug Is

`configurable_indel` picks an indel size `csize` sampled from
`[MUTATION_INDEL_MIN_SIZE, MUTATION_INDEL_MAX_SIZE]`, then computes an iterator
range as `repr.begin() + (repr.size() - csize)`. Both `repr.size()` and `csize`
are unsigned (`std::size_t`). If `csize >= repr.size()` — which can happen after
repeated deletions shrink the genome near `REPRESENTATION_MIN_SIZE` — the
subtraction wraps around to a very large positive value, producing an iterator
far past the end of the genome. This triggers undefined behavior (likely a
segfault or heap corruption). The same underflow applies to both the insertion
path (line 80) and the deletion path (line 88).

### Fix

Add a size guard before each use of the range:

```cpp
if (csize >= repr.size()) return;
```

Insert this check immediately after `csize` is computed, before any iterator
arithmetic.

---

## Bug 2 — Division by Zero in `task_switch_tracking` (ealib-modern)

| Field | Value |
|-------|-------|
| **File** | `ealib-modern/libea/include/ea/digital_evolution/utils/task_switching.h`, line 161 |
| **Severity** | Critical |
| **Confidence** | High |
| **Active in** | `ts_mt.cpp`, `gls.cpp`, `mt_lr_gls.cpp`, `mt_lr_gls_dol_control.cpp` → all four corresponding executables |

### What the Bug Is

The `task_switch_tracking` data recorder accumulates a per-organism count `org`
and then computes `ts /= org` to get a per-organism average. There is no check
for `org == 0.0`. If all subpopulations are empty (e.g., at initialization or
after a population collapse), the division produces `NaN` or `Inf`, which is
silently written to the data file. Note that the older local version in
`src/ts.h` lines 112–113 had the correct guard (`if (org > 0)`), which was lost
when the code was refactored into ealib-modern.

### Fix

Wrap the division in a zero-check:

```cpp
if (org > 0) {
    ts /= org;
}
```

---

## Bug 3 — `ts.cpp` / `ts.h` Use a Stale API Incompatible with ealib-modern

| Field | Value |
|-------|-------|
| **File** | `src/ts.h` line 52; `src/ts.cpp` throughout |
| **Severity** | High (won't compile) |
| **Confidence** | High |
| **Active in** | `ts.cpp` → `ts` executable (if compiled against ealib-modern) |

### What the Bug Is

`ts.h` declares `task_switching_cost` inheriting from `task_performed_event<EA>`
(line 52). This class does not exist in ealib-modern; the correct base class is
`reaction_event<EA>` (see `task_switching.h` line 69 in ealib-modern). Beyond
the inheritance issue, `ts.cpp` also uses:

- `namespace ea::` — ealib-modern uses `namespace ealib::`
- `abstract_configuration<EA>` — ealib-modern uses `default_lifecycle`
- Old template parameters: `digital_evolution<ts_configuration, spatial, empty_neighbor, round_robin>`
- Old metapopulation API: `meta_population` with `subpopulation_founder`
- Old event registration signature: `add_event<ts_replication>(this, ea)` — the `this` argument was removed

The entire `ts.cpp` / `ts.h` pair reflects an older version of the library and
will not compile against ealib-modern.

### Fix

Either:
1. Rewrite `ts.cpp` against the modern API (using `ts_mt.cpp` as a reference), or
2. Remove `ts.cpp` / `ts.h` from the build if they are no longer active

---

## Bug 4 — `FLAG` Metadata Key Used but Never Declared

| Field | Value |
|-------|-------|
| **File** | `src/lod_control_analysis.h`, lines 75, 78, 86 |
| **Severity** | High (won't compile) |
| **Confidence** | High |
| **Active in** | Any executable that includes `lod_control_analysis.h` (currently none active, but latent) |

### What the Bug Is

`lod_control_analysis.h` calls `get<FLAG>(**j, -1)` in three places, but `FLAG`
is never declared with `LIBEA_MD_DECL` anywhere in AvidaMT or ealib-modern. Any
translation unit that includes this header will fail to compile with an
undeclared identifier error.

### Fix

Add a metadata declaration at the top of `lod_control_analysis.h`:

```cpp
LIBEA_MD_DECL(FLAG, "ea.mt.flag", int);
```

---

## Bug 5 — Unregistered ISA Instructions in `multibirth_selfrep_prop1_remote_ancestor`

| Field | Value |
|-------|-------|
| **File** | `src/multi_birth_selfrep_not_remote_ancestor.h`, lines 148–151 |
| **Severity** | High |
| **Confidence** | High |
| **Active in** | Any executable using `multibirth_selfrep_prop1_remote_ancestor` as a starting genome |

### What the Bug Is

The ancestor body hardcodes instructions `if_not_member_start_propagule` and
`flag_1`, looked up via `ea.isa()["if_not_member_start_propagule"]` and
`ea.isa()["flag_1"]`. Neither instruction is registered in any active ISA
configuration (none of `ts_mt.cpp`, `gls.cpp`, `mt_lr_gls.cpp`, or
`mt_lr_gls_dol_control.cpp` register them), and they do not appear anywhere in
ealib-modern. Using this ancestor at runtime will crash or silently insert
garbage opcodes into the starting genome.

### Fix

Either register the missing instructions in the ISA configuration of any
executable that uses this ancestor, or replace the ancestor body with
instructions that are actually registered.

---

## Bug 6 — Infinite Loop / UB in Propagule Placement When Grid Is Full

| Field | Value |
|-------|-------|
| **File** | `src/ts_replication_propagule.h`, lines 312–363 (also lines 132–183 for the hetero variant) |
| **Severity** | Critical |
| **Confidence** | Medium |
| **Active in** | `ts_mt.cpp`, `mt_lr_gls.cpp`, `mt_lr_gls_dol_control.cpp` → three executables |

### What the Bug Is

During propagule placement, the code maintains a set
`used_pos_with_avail_neighbors` of grid positions that still have free
neighbors. Each iteration erases exhausted positions from the set (line 353).
If the set becomes empty (grid is completely full), the `while (not_placed)`
loop on line 312 becomes infinite because no exit condition handles the empty
case.

Additionally, before the set empties, line 313 calls:

```cpp
mea.rng().uniform_integer(0, used_pos_with_avail_neighbors.size())
```

With `size() == 0`, this calls `uniform_integer_rng(0, -1)`, which is undefined
behavior in Boost's uniform int distribution. The same bug exists in
`ts_replication_propagule_hetero` at lines 132–183.

### Fix

Add an early exit at the top of the `while (not_placed)` loop:

```cpp
if (used_pos_with_avail_neighbors.empty()) break;
```

---

## Bug 7 — ISA Lookup for `"input"` Always Fails in "Unfixed" Ancestor Variants

| Field | Value |
|-------|-------|
| **File** | `src/multi_birth_selfrep_not_remote_ancestor.h`, lines 95–96 and 292–293 |
| **Severity** | Medium |
| **Confidence** | High |
| **Active in** | Any executable using the unfixed ancestor variants |

### What the Bug Is

The "unfixed" ancestor variants (`multibirth_selfrep_not_remote_ancestor_unfixed`
and `multibirth_selfrep_not_remote_unfixed_ancestor`) look up the instruction
`"input"` via `ea.isa()["input"]`. However, all active configurations register
`fixed_input`, not `input`. The ISA `[]` operator will either throw or return a
default/garbage opcode when the name is not found, silently producing an
incorrect starting genome.

### Fix

Change `"input"` to `"fixed_input"` in these ancestor variants, or register the
`input` instruction in any configuration that uses these ancestors.

---

## Bug 8 — Off-by-One in Direction Iteration During Propagule Placement

| Field | Value |
|-------|-------|
| **File** | `src/ts_replication_propagule.h`, lines 140 and 320 |
| **Severity** | Medium |
| **Confidence** | High |
| **Active in** | `ts_mt.cpp`, `mt_lr_gls.cpp`, `mt_lr_gls_dol_control.cpp` → three executables |

### What the Bug Is

The loop condition is `while (dir_try <= 4)`, which iterates 5 times (values
0, 1, 2, 3, 4). There are only 4 cardinal directions (N=0, E=1, S=2, W=3). The
extra iteration (value 4) wraps around and re-checks one direction, wasting
work and potentially skewing placement direction bias.

### Fix

Change the condition to `while (dir_try < 4)`.

---

## Bug 9 — Offspring Subpopulation Not Initialized in `gls_replication`

| Field | Value |
|-------|-------|
| **File** | `src/gls.h`, around line 453 |
| **Severity** | Medium |
| **Confidence** | Medium |
| **Active in** | `gls.cpp` → `gls` executable |

### What the Bug Is

`gls_replication::operator()` calls `ea.make_individual()` to create a new
offspring subpopulation but never calls `p->initialize(ea.md())` or
`p->reset_rng(ea.rng().seed())`. The analogous function `gls_replication_ps`
(lines 619–621) does call both. Without initialization, the offspring
subpopulation uses default metadata values rather than inheriting the parent's
configuration, which can silently change critical parameters like mutation rates,
population sizes, and resource amounts.

### Fix

Add after `auto p = ea.make_individual()`:

```cpp
p->initialize(ea.md());
p->reset_rng(ea.rng().seed());
```

---

## Bug 10 — `uniform_integer()` Used as RNG Seed; Can Produce Zero → Non-Determinism

| Field | Value |
|-------|-------|
| **File** | `src/mt_propagule_orig.h` line 731; `src/lod_knockouts_fitness.h` line 200; multiple other sites |
| **Severity** | Medium |
| **Confidence** | High |
| **Active in** | `mt_lr_gls.cpp`, `mt_lr_gls_dol_control.cpp`, `gls.cpp` → three executables |

### What the Bug Is

`rng.uniform_integer()` with no arguments returns a value in
`[INT_MIN, INT_MAX]`, which includes zero and negative numbers. The `rng::reset()`
method interprets a seed of zero as "use `std::time(0)` instead", introducing
non-determinism into otherwise reproducible runs. Negative values are silently
cast to large unsigned ints, which is not UB but is likely unintended.

The `rng::seed()` method exists precisely for this use case; it returns values
in `[1, INT_MAX - 1)`, which are always valid deterministic seeds.

### Fix

Replace all `rng.uniform_integer()` calls used as seeds with `rng.seed()`:

```cpp
// Before:
p->reset_rng(mea.rng().uniform_integer());
// After:
p->reset_rng(mea.rng().seed());
```

---

## Bug 11 — Duplicate `LIBEA_MD_DECL` for Shared Metadata Keys (ODR Risk)

| Field | Value |
|-------|-------|
| **File** | `src/lod_control_analysis.h` line 23 and `src/lod_knockouts.h` line 23 (for `ARCHIVE_OUTPUT_SIZE`); `src/ts.h` lines 39–43 and ealib-modern `task_switching.h` lines 49–52 (for `TASK_SWITCHING_COST`, `LAST_TASK`, `NUM_SWITCHES`, `GERM_MUTATION_PER_SITE_P`) |
| **Severity** | Low (latent compile error) |
| **Confidence** | High |
| **Active in** | Latent — would manifest if these headers are co-included in the same translation unit |

### What the Bug Is

Multiple headers declare the same metadata keys with `LIBEA_MD_DECL`. If any two
of the conflicting headers are included in the same translation unit, the
compiler will emit a redefinition error. Currently the layout of includes
happens to avoid this, making it a latent issue. The `ts.h` duplicates are
especially likely to cause problems if `ts.h` is ever included alongside the
modern `task_switching.h`.

### Fix

Consolidate shared metadata declarations into a single header (e.g.,
`mt_metadata.h`) and have all other headers include that instead of redeclaring.

---

## Bug 12 — `quiet_nan` Used as Recombination Operator Template Argument

| Field | Value |
|-------|-------|
| **File** | `src/mt_lr_gls.cpp` line 188; `src/mt_lr_gls_dol_control.cpp` line 188 |
| **Severity** | Low (currently safe; wrong if recombination is ever enabled) |
| **Confidence** | Medium |
| **Active in** | `mt_lr_gls.cpp` → `mt_lr_gls` executable; `mt_lr_gls_dol_control.cpp` → `mt_lr_gls_dol_control` executable |

### What the Bug Is

The `metapopulation` typedef passes `quiet_nan` as the 4th template parameter,
which is the `RecombinationOperator` slot. `quiet_nan` is a fitness function, not
a recombination operator. This compiles and runs correctly only because
`isolated_subpopulations` never invokes recombination. If the generational model
were changed to one that does invoke recombination, this would produce a
type-error or runtime crash.

### Fix

Replace `quiet_nan` with `recombination::no_recombination` (or the appropriate
ealib-modern no-op recombination type) in the metapopulation typedef.

---

## Bug 13 — Dead Code: Offspring Iterators Computed but Discarded in `h_divide_remote`

| Field | Value |
|-------|-------|
| **File** | `src/mt_propagule_orig.h`, lines 89–92 |
| **Severity** | Low (dead code, no behavioral impact) |
| **Confidence** | Medium |
| **Active in** | `mt_lr_gls.cpp`, `mt_lr_gls_dol_control.cpp` → two executables |

### What the Bug Is

`h_divide_remote` computes iterators `f` and `l` to delimit the offspring
genome, but the line that actually constructs the offspring genome
(`typename Hardware::genome_type offr(f, l)`) is commented out. The iterators
are never used. The intended behavior — where a remote divide triggers group
reproduction using a germ cell rather than the actual division offspring — is
handled separately by the `mt_propagule` event handler. The dead iterator
computation suggests an incomplete refactor.

### Fix

Remove the unused `f` and `l` iterator computations, or add a comment
explaining why offspring genome construction is intentionally skipped.

---

## Bug 14 — `mean()` Called on Possibly-Empty Accumulator in `mt_propagule`

| Field | Value |
|-------|-------|
| **File** | `src/mt_propagule_orig.h`, lines 560 and 572 |
| **Severity** | Low |
| **Confidence** | Medium |
| **Active in** | `mt_lr_gls.cpp`, `mt_lr_gls_dol_control.cpp`, `gls.cpp` → three executables |

### What the Bug Is

The `gen` accumulator is populated inside a loop over `mea`. If `mea` has zero
subpopulations (e.g., at startup or after a complete population collapse),
`mean(gen)` is called on an empty accumulator. Boost accumulators return NaN for
`mean` on an empty set, which then gets written to the data file, silently
corrupting output.

### Fix

Wrap the `mean(gen)` call in a population size check:

```cpp
if (mea.size() > 0) {
    // write mean(gen)
}
```

---

## Bug 15 — Variable Shadowing in `lod_fitness_combo`

| Field | Value |
|-------|-------|
| **File** | `src/lod_knockouts_fitness.h`, lines 386–387 and 463 |
| **Severity** | Low |
| **Confidence** | High |
| **Active in** | Whichever executable includes `lod_knockouts_fitness.h` |

### What the Bug Is

Inside a nested loop, `int cur_update = 0` and `float total_workload = 0` are
redeclared, shadowing identically-named variables in the outer scope (declared
at lines 236 and 250 respectively). The inner declarations are likely intended
to be assignments to the outer variables, not new declarations. This compiles
correctly but the outer variables are not updated as intended, potentially
producing wrong loop behavior in the outer context.

### Fix

Remove the type specifier from the inner declarations to make them assignments:

```cpp
// Before (inner loop):
int cur_update = 0;
float total_workload = 0;
// After:
cur_update = 0;
total_workload = 0;
```

---

## Bug 16 — `ts_mt.cpp` Header Comment Names Wrong File

| Field | Value |
|-------|-------|
| **File** | `src/ts_mt.cpp`, line 1 |
| **Severity** | Low (documentation only) |
| **Confidence** | High |
| **Active in** | N/A |

### What the Bug Is

The opening comment block says `/* ts_soft_reset.cpp` but the file is
`ts_mt.cpp`. This is a copy-paste artifact that could mislead anyone searching
for `ts_soft_reset.cpp` or assuming the file's described behavior matches its
actual content.

### Fix

Change the comment to `/* ts_mt.cpp`.

---

## Bug 17 — Duplicate `#include` Directives in `ts_mt.cpp`

| Field | Value |
|-------|-------|
| **File** | `src/ts_mt.cpp`, lines 27 and 33 (for `subpopulation_founder.h`); lines 34 and 39 (for `line_of_descent.h`) |
| **Severity** | Low (no behavioral impact due to header guards) |
| **Confidence** | High |
| **Active in** | N/A |

### What the Bug Is

`subpopulation_founder.h` and `line_of_descent.h` are each `#include`d twice in
`ts_mt.cpp`. Header guards prevent actual compilation issues, but the duplicates
indicate copy-paste errors and add noise to the include list.

### Fix

Remove the duplicate `#include` lines.

---

## Summary Table

| # | File | Lines | Severity | Confidence | Active Executables |
|---|------|-------|----------|------------|-------------------|
| 1 | `src/gls.h` | 80–90 | Critical | High | `gls` |
| 2 | ealib-modern `task_switching.h` | 161 | Critical | High | `ts_mt`, `gls`, `mt_lr_gls`, `mt_lr_gls_dol_control` |
| 3 | `src/ts.h`, `src/ts.cpp` | 52, throughout | High | High | `ts` (won't compile) |
| 4 | `src/lod_control_analysis.h` | 75, 78, 86 | High | High | None active (latent) |
| 5 | `src/multi_birth_selfrep_not_remote_ancestor.h` | 148–151 | High | High | Any using prop1 ancestor |
| 6 | `src/ts_replication_propagule.h` | 132–183, 312–363 | Critical | Medium | `ts_mt`, `mt_lr_gls`, `mt_lr_gls_dol_control` |
| 7 | `src/multi_birth_selfrep_not_remote_ancestor.h` | 95–96, 292–293 | Medium | High | Any using unfixed ancestors |
| 8 | `src/ts_replication_propagule.h` | 140, 320 | Medium | High | `ts_mt`, `mt_lr_gls`, `mt_lr_gls_dol_control` |
| 9 | `src/gls.h` | ~453 | Medium | Medium | `gls` |
| 10 | `src/mt_propagule_orig.h`, `src/lod_knockouts_fitness.h` | 731, 200 | Medium | High | `mt_lr_gls`, `mt_lr_gls_dol_control`, `gls` |
| 11 | `src/lod_control_analysis.h`, `src/lod_knockouts.h`, `src/ts.h` | 23, 39–43 | Low | High | Latent (co-include conflict) |
| 12 | `src/mt_lr_gls.cpp`, `src/mt_lr_gls_dol_control.cpp` | 188 | Low | Medium | `mt_lr_gls`, `mt_lr_gls_dol_control` |
| 13 | `src/mt_propagule_orig.h` | 89–92 | Low | Medium | `mt_lr_gls`, `mt_lr_gls_dol_control` |
| 14 | `src/mt_propagule_orig.h` | 560, 572 | Low | Medium | `mt_lr_gls`, `mt_lr_gls_dol_control`, `gls` |
| 15 | `src/lod_knockouts_fitness.h` | 386–387, 463 | Low | High | Whichever includes this header |
| 16 | `src/ts_mt.cpp` | 1 | Low | High | N/A |
| 17 | `src/ts_mt.cpp` | 27, 33–34, 39 | Low | High | N/A |
