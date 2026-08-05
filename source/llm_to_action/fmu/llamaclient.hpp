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