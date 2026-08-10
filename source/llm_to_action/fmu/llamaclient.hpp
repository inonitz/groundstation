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
        /* Force the response to be a JSON array of objects -- llama-server converts this
           to a GBNF grammar server-side and constrains sampling with it, so the model
           CANNOT emit markdown fences or prose around the plan anymore. This is the real
           fix for the plan-parsing problem: extractJsonArray() (plan_parse.hpp) becomes a
           defense-in-depth backstop instead of the primary line of defense. Deliberately
           left loose (bare "array of objects", no per-action property schema) so it does
           not need to track every action type's exact fields and reject valid variations;
           translateToBaseCommands() already validates/drops unrecognized actions safely.
           Verified empirically against this exact model+mmproj+llama-server combination
           with a real multimodal (image+text) request before wiring in -- see
           docs/NOTES.md 2026-08-09. */
        m_jsonRequest["response_format"] = {
            {"type", "json_schema"},
            {"json_schema", {
                {"name", "flight_plan"},
                {"schema", {
                    {"type", "array"},
                    {"items", {{"type", "object"}}},
                    {"minItems", 1}
                }}
            }}
        };
        return;
    }


    __force_inline void destroy() {
        m_client.destroy();
        return;
    }

    auto send(
        std::string_view systemPrompt, 
        std::string_view userPrompt, 
        std::string_view imageB64Blob
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

        return m_client.submit(m_jsonRequest);
    }
private:
    llamaClient    m_client;
    std::string    m_systemPrompt;
    nlohmann::json m_jsonRequest;
    float          m_temperature = 0.1;
    uint32_t       m_maxTokens;

};