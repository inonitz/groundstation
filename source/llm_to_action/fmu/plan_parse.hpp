#pragma once
#include <string>
#include <string_view>

/*
    ROS-free extraction of the outermost JSON array from a VLM completion.

    Qwen3-VL (and most instruct models) wrap the plan in markdown fences
    (```json ... ```) or prefix it with prose ("Sure, here is the plan: [...]").
    A raw nlohmann::json::parse on that whole string is_discarded()s and the plan
    is silently dropped. We slice from the first '[' to the last ']' inclusive --
    the outermost array -- which survives fences, prose, and nested arrays.

    Returns "" when there is no array to parse (caller warns + skips).
    Header-only + standard-library-only so it is unit-testable with a bare g++.
*/
inline std::string extractJsonArray(std::string_view s) {
    std::string_view::size_type a = s.find('[');
    std::string_view::size_type b = s.rfind(']');
    if (a == std::string_view::npos || b == std::string_view::npos || b < a) {
        return std::string{};
    }
    return std::string(s.substr(a, b - a + 1));
}
