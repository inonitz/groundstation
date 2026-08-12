#include <nlohmann/json.hpp>
#include <util2/C/macro.h>
#include <httplib.h>
#include <optional>
#include <string>
#include <functional>
#include <future>
#include "threadpool.hpp"


typedef std::function<void(httplib::Result&)> httpRequestCallback;
typedef std::future<httplib::Result>          httpRequestFuture;
typedef std::optional<httpRequestFuture>      OptionalHttpRequestFuture;


class llamaClient {
public:
    llamaClient() noexcept = default;
    ~llamaClient() noexcept { destroy(); }

    void create(const std::string& host = "127.0.0.1", uint16_t port = 8080);
    void destroy();
    
    void submit(
        nlohmann::json const&      payload, 
        httpRequestCallback const& callback
    );
    [[nodiscard]] OptionalHttpRequestFuture submit(const nlohmann::json& payload);

private:
    static constexpr const char* mk_contentType     = "application/json";
    static constexpr const char* mk_contentEndpoint = "/v1/chat/completions";

    ThreadPool                       m_pool;
    std::unique_ptr<httplib::Client> m_cli;
    std::string                      mk_host;
    httplib::Headers                 mk_Headers;
};


/* 
    This one is less primitive than the first.
    If granular control is required use the llamaClient.
    If you just want to send user-queries & receive responses from the model use this instead.
*/
class llamaClientConnection {
public:
    __force_inline void create(
        std::string const& initialSystemPrompt,
        float              temperature = 0.1,
        uint32_t           max_tokens  = 256
    ) {
        m_systemPrompt = initialSystemPrompt.empty() ? 
            "You are a direct automation tool. Output only the requested answer." 
            : 
            initialSystemPrompt;
        m_temperature  = temperature;
        m_maxTokens    = max_tokens;

        m_client.create();
        m_jsonRequest["temperature"] = m_temperature;
        m_jsonRequest["max_tokens"]  = m_maxTokens;
        /* The plan grammar (GBNF, "grammar" field) is built per-send in send(), conditioned on
           whether the drone is grounded so takeoff can be pinned as the first action.
           See buildPlanGrammar / docs/NOTES.md 2026-08-10. */
        return;
    }


    __force_inline void destroy() {
        m_client.destroy();
        return;
    }

    auto send(
        std::string_view systemPrompt, 
        std::string_view userPrompt, 
        std::string_view imageB64Blob,
        bool             requireTakeoffFirst
    ) {
        std::string sys_prompt = systemPrompt.empty() ? m_systemPrompt : std::string(systemPrompt);

        /* Text block always; image block ONLY when we actually have a frame.
           An image_url with an empty base64 payload makes the VLM server reject
           the request (fast 400) -- that is the text-only / no-camera path. */
        nlohmann::json userContent = nlohmann::json::array();
        userContent.push_back({ {"type", "text"}, {"text", std::string(userPrompt)} });
        if (!imageB64Blob.empty()) {
            userContent.push_back({ {"type", "image_url"},
                {"image_url", {{ "url", "data:image/jpeg;base64," + std::string(imageB64Blob) }}} });
        }
        m_jsonRequest["messages"] = nlohmann::json::array({
            { {"role", "system"}, { "content", sys_prompt } },
            { {"role", "user"  }, { "content", userContent } }
        });

        m_jsonRequest["grammar"] = buildPlanGrammar(requireTakeoffFirst);

        return m_client.submit(m_jsonRequest);
    }
    /* Plan grammar (GBNF). llama-server's json_schema path does NOT enforce const/prefixItems
       for this model+build -- verified adversarially: the model ignored a takeoff const and
       planned 'go' first, exactly the failure that stranded the drone on the ground. A raw
       GBNF passed via "grammar" IS enforced token-by-token, so we hand-write it. Shape: a
       mandated {"thought":...} object, then action objects whose "action" is one of the known
       verbs. When grounded (requireTakeoffFirst) the SECOND element is pinned to the literal
       {"action":"takeoff"} -- deterministic, cannot be violated. Every string and the action
       count are length-bounded so a runaway thought cannot blow past max_tokens and truncate
       the array. Verified adversarially against this exact model+mmproj+llama-server: const is
       ignored, grammar+bounds give 4/4 takeoff-first with no truncation. See docs/NOTES.md 2026-08-10. */
    static std::string buildPlanGrammar(bool requireTakeoffFirst) {
        static const char* kRootGrounded =
            R"GBNF(root    ::= "[" ws thought ws "," ws takeoff rest ws "]" ws
)GBNF";
        static const char* kRootAirborne =
            R"GBNF(root    ::= "[" ws thought (ws "," ws action){1,7} ws "]" ws
)GBNF";
        static const char* kCommon =
            R"GBNF(rest    ::= (ws "," ws action){0,6}
thought ::= "{" ws "\"thought\"" ws ":" ws tstring ws "}"
tstring ::= "\"" tchar{0,300} "\""
tchar   ::= [^"\\] | "\\" ["\\bfnrtu/]
takeoff ::= "{" ws "\"action\"" ws ":" ws "\"takeoff\"" ws "}"
action  ::= "{" ws "\"action\"" ws ":" ws verb (ws "," ws member){0,8} ws "}"
verb    ::= "\"takeoff\"" | "\"land\"" | "\"go\"" | "\"curve\"" | "\"rotate\"" | "\"orbit\"" | "\"approach\"" | "\"follow\"" | "\"stop\"" | "\"search\"" | "\"re-assess\""
member  ::= sstring ws ":" ws value
value   ::= sstring | number | "true" | "false" | "null"
sstring ::= "\"" tchar{0,160} "\""
number  ::= "-"? [0-9]+ ("." [0-9]+)?
ws      ::= [ \t\n]*
)GBNF";
        return std::string(requireTakeoffFirst ? kRootGrounded : kRootAirborne) + kCommon;
    }

private:
    llamaClient    m_client;
    std::string    m_systemPrompt;
    nlohmann::json m_jsonRequest;
    float          m_temperature = 0.1;
    uint32_t       m_maxTokens;

};