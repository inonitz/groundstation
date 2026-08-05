#include "../plan_parse.hpp"
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

    std::printf("plan_parse_test OK\n");
    return 0;
}
