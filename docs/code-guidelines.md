# Code Guidelines

Derived from sampling the user's own code: `speech_to_action` (feature-showcase-v2
branch), `sttserv`, `util2`, `inonitz/tree` (github repo), CPU thread/core manager gist
(github gist). Per project: 3 smallest + 3 biggest files, plus top/project
CMakeLists.txt. `inonitz/tree` ships `.clang-format`/`.clang-tidy` — used as ground
truth below, not guesswork.

## Design priorities

Every design/implementation decision should target, in this order of concern:
**simplicity, human readability, performance.** All three matter — performance isn't an
excuse to sacrifice the first two, and simplicity isn't an excuse to leave performance
on the table where it's cheap to have.

Follow the **KISS** and **YAGNI** principles when writing the code:

- **KISS (Keep It Simple):** pick the simplest design that solves the *actual* problem. The fewest moving parts a reader must hold at once beats a clever, general one.
- **YAGNI (You Aren't Gonna Need It):** implement only what a current requirement needs, not what it *might* need later. Speculative abstraction is a real cost paid now for a maybe.

A concrete consequence: keep code units small enough that a human can actually hold
them in working memory. Working memory holds roughly 3-7 discrete "chunks" at once
(the revised "magical number" range from cognitive load research), and this limit
doesn't budge just because the artifact is code. Practically:

- **~2000 LOC in one file is beyond what anyone can reason about as a single unit** — at that size you're not reading it, you're spot-checking it.
- **~400 LOC is roughly the practical ceiling** for reviewing/understanding a chunk of code in one sitting with good defect/issue detection. This isn't a guess — it's backed by the SmartBear/Cisco code review study (~2,500 reviews, ~3.2M LOC, one of the largest published studies on the subject): review effectiveness (70-90% defect discovery) held at 200-400 LOC reviewed at under ~300-500 LOC/hour; effectiveness drops sharply past that.
- **150-200 LOC is the preferred target** for a single file/unit that captures one general pattern — small enough to hold entirely in working memory, not just skim.
- This isn't a hard rule — some things (a generated header, a big enum/lookup table, a single cohesive algorithm) legitimately don't split cleanly. Use judgment; the goal is comprehension, not hitting a line count.

## Naming

- Types/classes: `PascalCase` (`AsyncKeyHook`, `CaptureDevice`, `ModelBackend`, `LogicalProcessor`).
- Public methods: `camelCase` (`bindKey`, `allocateProcessor`, `freeThread`).
- Private/internal helper functions (static methods, free functions doing OS-level work): often `PascalCase` instead (`ProcessCurrentConfiguration`, `GetProcessorNativeConfiguration`, `AVLTreeComputeHeight`). Rule of thumb: **public API surface = camelCase, internal/OS-facing helper = PascalCase is also acceptable** — both appear, pick based on what's already in the file.
- C API functions: `snake_case` or prefix+PascalCase, prefixed with lib name (`util2_thread_sleep`, `AVLTreeCreate`, `AVLTreeDestroy`). C code favors `LibraryPascalCase` function names; C++ favors `camelCase` methods.
- Member variables: prefixed `m_`, then `camelCase`: `m_running`, `m_exit`, `m_coreID`.
  - Prefix letters compose and each has a fixed meaning: **`m` = member, `b` = boolean, `k` = constant.**
    So `mb_` = a boolean member (`mb_translateEnglish`), `mk_` = a member that's effectively constant/config after construction (`mk_ChannelCount`), plain `m_` = ordinary member. A bare `k_`-prefixed name with no `m` is a non-member constant.
- Constants (non-member, namespace/global scope): `kPascalCase` (`kDefaultDroneDeviceID`, `kInferenceSampleRate`).
- Macros: `ALL_CAPS`, header guards are long descriptive `#ifndef __SCOPE_DESCRIPTION__` (not `#pragma once` consistently — both appear across every project sampled; prefer the guard style already in the file you're editing).
- Fixed-width types: `u8/u16/u32/u64/i8.../f32/f64` used everywhere instead of raw `int`/`float` (from `util2/C/base_type.h`), OR the standard `uint32_t`/`int8_t` forms in projects that don't depend on util2 (`tree`, the gist). Match whichever the surrounding project already uses — don't introduce util2 aliases into a project that isn't already pulling util2.

## Structure & idioms

- Explicit `return;` at the end of `void` functions, even when redundant. Confirmed deliberate: `inonitz/tree`'s `.clang-tidy` explicitly disables `modernize-use-trailing-return-type` and `readability-redundant-control-flow`, which would otherwise flag this.
- Debug logging via raw `fprintf(stderr/stdout, "[TAG] ...\n", ...)` with bracketed subsystem tags (`[WORKER]`, `[HOOK_DBG]`), or `RCLCPP_INFO/WARN/ERROR` in ROS2 nodes with the same tag convention. Not routed through an abstracted logger.
- Dead/legacy code is routinely left in as large commented-out blocks rather than deleted (seen in `sttserv/capture.cpp` AND in `tree/source/tree/C/avl_tree.c`'s commented-out `AVLTreeInsertOld`) — a consistent habit across every project, not a one-off. **Treat as intentional. Don't strip commented-out code you didn't just write, ask first.**
- WHY-comments over WHAT-comments — explain non-obvious reasoning (locking rationale, platform quirks, external references/citations), not restate the code. Struct field docs use a lightweight `@fieldName:\n    description` block comment above the struct rather than full Doxygen.
- Concurrency pattern: producer/consumer (often literally SPSC — single-producer/single-consumer) threads, `std::mutex` + `std::condition_variable` + `std::atomic<bool> m_exit`, explicit join in `destroy()`. This is the default shape for a genuinely two-actor concurrent pipeline because it's simple to reason about — **use it when the use case actually is SPSC-shaped; if the concurrency pattern doesn't fit (more than one producer/consumer, work-stealing, lock-free needs, etc.), don't force it, use whatever pattern actually fits.**
- Singleton-via-atomic-pointer + `std::atomic_flag` guard, used specifically for OS callback contexts needing a global instance (Windows hook callback, etc).
- Platform branching via `#if defined(UTIL2_OS_WINDOWS) / UTIL2_OS_LINUX` (or `_WIN32` / `__linux__` in projects without util2) inline, both implementations live side by side in the same file/function rather than separate per-platform files.
- Manual init-state tracking via bitmask (`setInitState`/`isInit`) to allow partial-construction teardown in `destroy()` — this is the RAII substitute used instead of exceptions/smart-pointer chains for multi-step C-API resource setup.
- **No exceptions.** Propagate errors via status/error codes (or the init-state bitmask above), never `throw`. `try`/`catch` is allowed *only* to wrap a third-party API that throws — catch at that boundary and convert to a status code. Fatal config/invariant failures log (`RCLCPP_FATAL`/`fprintf`) then `std::abort()`; they do not throw.
- **No virtual calls.** No `virtual`/dynamic dispatch in the runtime path — prefer static polymorphism (templates/CRTP) or explicit tagged dispatch (the `GenericCommand` `id()` + `switch` pattern). Keeps dispatch predictable and vtable-free.
- `[[nodiscard]]` + `noexcept` used selectively on init-step / accessor functions that return `bool`/a computed value.
- Manual single-block allocation (`util2_aligned_malloc` sized to fit multiple sub-structs, sliced by offset) for cache-line-aligned, single-free resource groups — used in performance-sensitive audio/capture code, not the general default.
- Custom cast macros `__rcast`/`__scast` wrap `reinterpret_cast`/`static_cast`; `__carraysize` for array length; `__force_inline` wraps `__forceinline`/`__attribute__((always_inline))` per compiler. Use these instead of raw casts/inline keywords inside util2-adjacent code.
- `extern "C"` blocks are always wrapped via a generated macro pair (`UTIL2_EXTERNC_DECL_BEGIN/END`, `TREELIB_EXTERNC_DECL_BEGIN/END`, `STTSERVER_EXTERNC...` — same pattern, different prefix per project) rather than written by hand.
- Symbol visibility: each library defines its own `_API` export macro (`UTIL2_API`, `STTSERVER_API`, `TREELIB_API`) and a matching `_EXPORTS`/`_STATIC_DEFINE` compile definition pair, switched by `BUILD_SHARED_LIBS`.
- Heavy macro codegen for repetitive type families (e.g. `DEFINE_VECTOR_STRUCTURE` generating vec2/vec3/vec4 variants) — acceptable pattern for this codebase, don't "simplify" into templates unprompted.
- **Thin public header / heavy internal impl split**, used consistently for template-heavy code in `tree`: e.g. `tree/AVLTree.hpp` is a ~2-line file that just includes `tree/internal/AVLTreeGeneric.hpp` (declarations), and `tree/AVLTreeImpl.hpp` includes the matching `.tpp` (template definitions). Declaration and definition are separate files (`.hpp` + `.tpp`), letting a consumer include just the declaration if they don't need to instantiate. Follow this split for any new template-heavy public type.
- **Guard clauses over nesting.** Check the unlikely/exit condition first and bail immediately; don't nest the "normal path" inside successive `if` blocks.
  ```cpp
  // Preferred
  if (!cond) {
      return; // or continue / break / early exit
  }
  what_to_do_when_cond_holds();

  // Avoid
  if (cond) {
      if (other) {
          if (another) {
              // deeply nested "real" logic
          }
      }
  }
  ```

## Formatting

`inonitz/tree` ships `.clang-format`/`.clang-tidy` — treat these as the actual house
rule, not just this one repo's preference, since every hand-formatted sample elsewhere
is consistent with it:

- Indent width 4, **tabs for indentation, spaces for alignment** (`UseTab: ForIndentation`).
- **Column limit ~90-95 chars.** clang-format's `ColumnLimit: 0` only disables *automatic* wrapping — it does not mean "unlimited" in practice. Manually wrap any line that would exceed ~95 chars, using the patterns below.
- Pointers/refs left-aligned: `T* x`, not `T *x`.
- Consecutive assignments/declarations/macros are visually aligned on `=` (this is why constant blocks and struct member lists line up in columns — it's enforced, not incidental).
- `if (x)` has a space before `(`; function calls don't: `func(x)`.
- clang-tidy enables `llvm-*, bugprone-*, cert-*, clang-analyzer-*, concurrency-*, cppcoreguidelines-*, modernize-*, performance-*, portability-*, readability-*`, minus `modernize-use-trailing-return-type` and `readability-redundant-control-flow` (see explicit-`return;` note above).

### Wrapping long function calls (many arguments)

Default: open paren stays on the call line, each argument gets its own indented line,
closing paren + `;` goes back at the call's base indent.

```cpp
// Execute Manual Resampler
ma_resampler_process_pcm_frames(
    m_audioMan.resamplerHandle(),
    pReadBuffer,
    &framesToRead64,
    resampledBuf.data(),
    &framesToWrite64
);
```

Exception: if the first (or first two) arguments are important for readability/context,
keep those on the opening line and only indent the rest:

```cpp
if (!m_audioMan.selectDevicesAndFinalize(this, captureCallbackProducer, 1, 1, 16000,
        static_cast<uint8_t>(args.capture_id  == -1 ? 0xFF : args.capture_id),
        static_cast<uint8_t>(args.playback_id == -1 ? 0xFF : args.playback_id)
    )) {
    RCLCPP_ERROR(this->get_logger(), "Audio Driver Finalization failed");
}
```

When the whole `if (...)` condition itself would exceed the column limit, indent the
wrapped arguments/casts and put the closing `))` on its own line at the base indent
(as above) rather than trying to keep everything flat.

### Wrapping long `if` conditions (boolean logic)

Keep multiline, with `||`/`&&` aligned at the start of each continuation line, and use
extra parens to make grouping explicit: `( condition )`, or `( (condA) && (condB) )`.

```cpp
if (s.find("disarm") != std::string::npos || s.find("land") != std::string::npos) {
    doArm = true; newArm = false;
}
else if(
    s.find("arm") != std::string::npos
    || s.find("um") != std::string::npos
    || s.find("takeoff") != std::string::npos
    || s.find("take off") != std::string::npos
) {
    doArm = true; newArm = true;
}
```

## CMakeLists.txt

- `cmake_minimum_required` 3.16 for workspace-level in the older projects (groundstation, sttserv); `tree` uses 3.24 and relies on it (`FILE_SET` header sets, see below). Standalone libs (util2) may use 3.14. Use the newest floor a project already declares; don't downgrade it.
- Top-level `project()` name ends in `_workspace` (`groundstation_workspace`, `sttserver_workspace`) or is just `workspace` (`tree`); leaf/library project uses the real name (`sttserv`, `util2`, `treelib`).
- Standard top-level-detection boilerplate, copy verbatim into any new top-level CMakeLists:
  ```cmake
  if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
      set(<PREFIX>_IS_TOP_LEVEL ON)
  else()
      set(<PREFIX>_IS_TOP_LEVEL OFF)
  endif()
  ```
- Shared `cmake/` module includes reused across projects verbatim: `FetchCPM`, `SubmoduleUpdate`, `UseCCache`, `ColouredOutput`, `OutputDir`, `WorkspaceOptions`, `BuildDiagnostics`. If adding a new top-level project, pull these in rather than reinventing.
- `OPTION()` flags prefixed by project name (`STTSERVER_ENABLE_SANITIZER_ADDRESS`, `GROUNDSTATION_BUILD_TESTS`, `TREELIB_BUILD_TESTS`), with `BUILD_TESTS`/`BUILD_BENCHMARKS` defaulting to the `_IS_TOP_LEVEL` var so they're off when vendored as a dependency.
- Dependencies pulled via a custom `safe_cpm_add_package(NAME ... GIT_REPOSITORY ... GIT_TAG ... GIT_SHALLOW TRUE)` or, for vendored/local deps, `safe_cpm_add_package(NAME ... SOURCE_DIR ...)`. Always use this wrapper, not raw `FetchContent`/`CPMAddPackage`. (`tree`'s current CMakeLists doesn't use it yet — the older projects are the reference here.)
- Libraries always get an alias: `add_library(NAMESPACE::Target ALIAS project_name)` (`UTIL2::util2`, `STTSERVER::SpeechToTextServer`, `TREELIB::treelib`).
- `SOURCES`/`HEADERS` declared as explicit `set()` lists — no `GLOB`.
- `target_compile_features` set explicitly per target: `c_std_11` + `cxx_std_17`.
- Conditional composition (optional backends) done via generator expressions on an INTERFACE library (`$<$<BOOL:${OPT}>:...>` for sources/link libs/defines), not duplicated `if/else` target blocks.
- For repeated near-identical targets (multiple ROS2 node executables in one CMakeLists), define a local `macro()`/`function()` once and call it per target, rather than copy-pasting `add_executable` blocks.
- **Public/private header separation (CMake ≥ 3.24 only):** `tree`'s leaf CMakeLists splits `PUBLIC_HEADERS` (flat list, `target_sources(... PUBLIC ...)`) from `PRIVATE_HEADERS` (internal template impl details, attached via `target_sources(... INTERFACE FILE_SET project_internal_headers TYPE HEADERS BASE_DIRS include FILES ...)`, plus `VERIFY_INTERFACE_HEADER_SETS ON`). This is a newer, stricter convention than the flat `HEADERS` list used in `sttserv`/`util2`/groundstation. Use `FILE_SET` in new projects that can commit to CMake 3.24+; otherwise match the flat-list convention already in use.

## Review & commits

All code must be peer-reviewed by a human before it's committed — this includes code
written by an agent. An agent producing code is not a substitute for that review.

If an agent must generate the commit message itself, keep it short: 2-4 sentences,
resized down further for a small change. Describe the general idea/pattern of the
change, not a line-by-line recap — the diff is right there for anyone who wants to dig
deeper. Nobody needs a commit message to restate what the code already says.

## When unsure

If a file doesn't clearly match one of these patterns, don't force it — ask, or match
the nearest existing sibling file instead of inventing a new convention.
