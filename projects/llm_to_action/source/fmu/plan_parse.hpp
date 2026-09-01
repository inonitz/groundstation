#pragma once
#include <nlohmann/json.hpp>
#include <string>
#include <string_view>

/*
    ROS-free extraction of the outermost JSON array from a VLM completion.

    Qwen3-VL (and most instruct models) wrap the plan in markdown fences
    (```json ... ```) or prefix/suffix it with prose ("Sure, here is the plan:
    [...] let me know if you want changes!"). Qwen3-VL in particular tends to
    describe what it sees (bounding boxes, pixel coordinates) in that prose,
    so the prose itself often contains stray '[' / ']' characters.

    A naive "first '[' to last ']'" slice breaks the moment ANY such stray
    bracket appears before the plan or after it: the slice then contains
    trailing/leading garbage, nlohmann::json::parse() rejects the whole thing
    (trailing-content-after-value is a parse error), and a perfectly good
    plan gets silently dropped -- observed live 2026-08-09: 10 consecutive
    dropped plans after an ORBIT completed, drone held hover for ~2 minutes
    with no path back to LAND because every plan discard just re-asks the
    VLM instead of surfacing the raw text anywhere. See docs/NOTES.md.

    Fix: try each '[' in the string in turn. For each, walk forward with
    quote-aware bracket-depth counting (so a literal "[" inside a JSON string
    value doesn't miscount) to find ITS matching ']'. Parse that candidate
    span; if it's valid JSON and an array, return it. If not (either the
    brackets never balance, or they balance but aren't valid JSON -- e.g. a
    prose aside like "[roughly centered]"), move on to the next '[' and try
    again. This survives stray brackets on either side of the real plan, not
    just after it.

    Returns "" when no candidate parses as an array (caller warns + skips).
*/
inline std::string extractJsonArray(std::string_view s) {
    for (std::string_view::size_type start = s.find('['); start != std::string_view::npos;
         start                             = s.find('[', start + 1)) {
        int  depth    = 0;
        bool inString = false;
        bool escape   = false;
        std::string_view::size_type end = std::string_view::npos;

        for (std::string_view::size_type i = start; i < s.size(); ++i) {
            char c = s[i];
            if (inString) {
                if (escape) {
                    escape = false;
                } else if (c == '\\') {
                    escape = true;
                } else if (c == '"') {
                    inString = false;
                }
                continue;
            }
            if (c == '"') {
                inString = true;
            } else if (c == '[') {
                ++depth;
            } else if (c == ']') {
                --depth;
                if (depth == 0) {
                    end = i;
                    break;
                }
            }
        }
        if (end == std::string_view::npos) {
            continue;  /* unbalanced from this start -- try the next '[' */
        }

        std::string candidate(s.substr(start, end - start + 1));
        auto        parsed = nlohmann::json::parse(candidate, nullptr, false);
        if (!parsed.is_discarded() && parsed.is_array()) {
            return candidate;
        }
        /* balanced but not valid JSON (or not an array) -- e.g. a prose
           aside like "[roughly centered]" -- keep looking. */
    }
    return std::string{};
}
