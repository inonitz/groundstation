#include "fmu/plan_parse.hpp"
#include <cassert>
#include <cstdio>
#include <string>

int main() {
    /* Bare array passes through untouched. */
    assert(extractJsonArray(R"([{"action":"takeoff"}])") == R"([{"action":"takeoff"}])");

    /* Markdown-fenced (the common Qwen3-VL shape). */
    assert(extractJsonArray("```json\n[{\"action\":\"land\"}]\n```") == R"([{"action":"land"}])");

    /* Prose prefix + suffix. */
    assert(extractJsonArray("Sure, here is the plan: [1,2,3] hope it helps!") == "[1,2,3]");

    /* Nested arrays: outermost bracket pair is kept whole. */
    assert(extractJsonArray(R"(noise [{"a":[1,2]},{"b":[3]}] tail)") == R"([{"a":[1,2]},{"b":[3]}])");

    /* No array at all -> empty. */
    assert(extractJsonArray("no array here").empty());

    /* A lone object (not an array) -> empty (caller expects an array). */
    assert(extractJsonArray(R"({"action":"takeoff"})").empty());

    /* Empty / whitespace -> empty. */
    assert(extractJsonArray("").empty());
    assert(extractJsonArray("   \n  ").empty());

    /* Trailing prose with a stray bracket AFTER the real plan (a friendly
       aside referencing something bracketed) -- the old first-'['-to-last-']'
       slice swallowed the aside and broke; must stop at the plan's own close. */
    assert(extractJsonArray(R"([{"action":"land"}] see the diagram [here] for reference)")
           == R"([{"action":"land"}])");

    /* Leading prose with a stray, non-JSON bracketed aside BEFORE the real
       plan (Qwen3-VL describing what it sees before giving the plan) --
       the old code grabbed from that first '[' onward and broke; must skip
       the aside (it doesn't parse as JSON) and find the real array after it. */
    assert(extractJsonArray("I see the car at [roughly center-frame]. Plan: [{\"action\":\"land\"}]")
           == R"([{"action":"land"}])");

    /* Both at once: leading AND trailing stray brackets around the real plan. */
    assert(extractJsonArray("Target [approx] found. [{\"action\":\"land\"}] done, see [note].")
           == R"([{"action":"land"}])");

    std::printf("plan_parse_test OK\n");
    return 0;
}
