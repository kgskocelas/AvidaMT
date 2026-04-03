# AvidaMT Crash Bug Fix Plan

**What's happening:** The simulation crashes with a memory error (SEGV) mid-run. The crash happens when an organism tries to execute an instruction, but the instruction code stored in its genome points to a slot in the instruction set that doesn't exist. C++ reads garbage memory from beyond the end of a list, and the program blows up.

---

## Bug 1: The Config File Allows Invalid Instruction Numbers

### What's going on (plain English)

Think of the instruction set as a menu at a restaurant with 33 items (numbered 0–32). An organism's genome is like a list of menu item numbers — each number tells the organism which "dish" (instruction) to cook next.

The problem: the mutation system that creates new organisms (the "germ-line" mutation used when a group splits to form a new group) is configured to randomly pick menu item numbers between **0 and 37**. But the menu only goes up to **32** (33 items total). So sometimes an organism ends up with a genome containing numbers like 33, 34, 35, 36, or 37 — items that don't exist on the menu.

When that organism tries to execute instruction #35 (for example), the code reaches past the end of the instruction list and grabs whatever random data happens to be in memory there. That random data gets treated as a pointer, the program tries to follow it, and it crashes.

### Where is the bug?

**File:** `AvidaMT/etc/ts_mt.cfg`, lines 24–25

```
uniform_integer.min=0   # inclusive of zero
uniform_integer.max=38  # exclusive of max
```

This config tells the germ-line mutation to pick random integers from **0 up to (but not including) 38**, i.e., `[0, 37]`.

But in `AvidaMT/src/ts_mt.cpp` (lines 59–93), `lifecycle::after_initialization` registers exactly **33 instructions** into the instruction set (indices 0–32):

```
nop_a, nop_b, nop_c, nop_x, mov_head, if_label, h_search, nand,
push, pop, swap, inc, dec, tx_msg_check_task, tx_msg, rx_msg,
bc_msg, rotate, rotate_cw, rotate_ccw, if_less, h_alloc, h_copy,
fixed_input, output, donate_res_to_group, get_xy, if_equal,
if_not_equal, jump_head, is_neighbor, h_divide_remote, h_divide_local
```

Instruction numbers **33 through 37 do not exist**, but the config allows them to be written into genomes.

This config value is used by `configurable_per_site` (defined in `ealib-modern/libea/include/ea/digital_evolution/utils/configurable_mutation.h`), which is called inside `mt_propagule::operator()` in `AvidaMT/src/mt_propagule_orig.h` (line 479):

```cpp
configurable_per_site m(get<GERM_MUTATION_PER_SITE_P>(mea));
// ...
mutate(*q, m, *p);   // <-- this mutation can write codes 33-37 into the genome
```

### How to fix it

**Step 1:** Open `AvidaMT/etc/ts_mt.cfg`.

**Step 2:** Change line 25 from:
```
uniform_integer.max=38  # exclusive of max
```
to:
```
uniform_integer.max=33  # exclusive of max; must equal the number of instructions in the ISA
```

**Why 33?** The code internally does `max - 1` before using the value, so setting `max=33` means the mutation will pick numbers in `[0, 32]`, which are exactly the valid instruction indices.

**Step 3:** Rebuild and rerun. This alone should prevent new organisms from being born with invalid instruction codes, which is the root cause of the crash.

---

## Bug 2: The Instruction Lookup Has No Safety Check

### What's going on (plain English)

Even after fixing Bug 1, it's good practice to add a safety net. Right now, if any instruction code in a genome is ever out of range (whether from this bug, a bad save file, or a future mistake), the code silently reads garbage memory and crashes with a confusing error. Instead, it should stop immediately with a clear message explaining what went wrong — just like the string-based lookup already does.

Imagine you ask a librarian for book number 500, but the library only has 33 books. Currently the librarian walks to shelf 500 (which doesn't exist), grabs whatever is there, and hands it to you. The fix is for the librarian to say "I only have books 0–32, you asked for 500 — something is wrong."

### Where is the bug?

**File:** `ealib-modern/libea/include/ea/digital_evolution/instruction_set.h`, lines 678–681

```cpp
//! Retrieve a pointer to instruction i.
inst_ptr_type operator[](std::size_t i) {
    return _isa[i];   // <-- no bounds check! reads garbage if i >= _isa.size()
}
```

Compare this to the string-based lookup right below it (lines 683–691), which *does* have a safety check:

```cpp
//! Retrieve the index of instruction inst.
std::size_t operator[](const std::string& inst) {
    name_map_type::iterator i=_name.find(inst);
    if(i ==_name.end()) {
        throw std::invalid_argument("could not find instruction: " + inst + " in the current ISA.");
    }
    return i->second;
}
```

### How to fix it

**Step 1:** Open `ealib-modern/libea/include/ea/digital_evolution/instruction_set.h`.

**Step 2:** Find the numeric `operator[]` at approximately line 678:

```cpp
//! Retrieve a pointer to instruction i.
inst_ptr_type operator[](std::size_t i) {
    return _isa[i];
}
```

**Step 3:** Replace it with this version that checks bounds first:

```cpp
//! Retrieve a pointer to instruction i.
inst_ptr_type operator[](std::size_t i) {
    if (i >= _isa.size()) {
        throw std::out_of_range("instruction index " + std::to_string(i) +
                                " is out of range (ISA size=" +
                                std::to_string(_isa.size()) + ")");
    }
    return _isa[i];
}
```

**What this does:** Before accessing the list at position `i`, it checks whether `i` is a valid index. If not, it throws an exception with a helpful message (e.g., `"instruction index 35 is out of range (ISA size=33)"`) instead of silently reading garbage memory.

**Step 4:** Make sure `<stdexcept>` is included at the top of the file (it should already be, but double-check). If not, add:
```cpp
#include <stdexcept>
```

**Step 5:** Rebuild. Now, if an invalid index is ever accessed, you'll get a clear error message pointing directly at the problem instead of a mysterious SEGV.

---

## Summary of Changes

| File | Change |
|---|---|
| `AvidaMT/etc/ts_mt.cfg` | Change `uniform_integer.max` from `38` to `33` |
| `ealib-modern/libea/include/ea/digital_evolution/instruction_set.h` | Add bounds check to `operator[](std::size_t i)` |

**Fix Bug 1 first** — it stops invalid instruction codes from ever entering genomes (the true root cause).

**Fix Bug 2 second** — it acts as a safety net that gives a clear error message if invalid codes somehow appear in the future (from a different code path, a corrupted checkpoint file, etc.).

---

## Why does the crash happen at that specific location?

For the curious: when the organism executes an instruction, it does:

```cpp
// hardware.h, line 194
typename EA::isa_type::inst_ptr_type inst = ea.isa()[_repr[_head_position[IP]]];
```

`_repr[_head_position[IP]]` is the instruction code at the current instruction pointer — say, `35`.

`ea.isa()[35]` calls `instruction_set::operator[](35)`, which does `_isa[35]`. Since `_isa` only has 33 elements, this reads memory that belongs to something else entirely. The data there happens to look like a `boost::shared_ptr` object (it has the right size), but the internal pointer it contains points to a nonsense memory address (a "high value address" as AddressSanitizer reports).

The code then copies this bogus `shared_ptr`, which requires incrementing a reference count at that nonsense address — and that's where the SEGV happens, in `boost::detail::atomic_increment(unsigned int*)`.
