#include "threadpool.hpp"
#include <nlohmann/json.hpp>
#include <util2/C/macro.h>
#include <httplib.h>
#include <optional>
#include <string>
#include <functional>
#include <future>


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


class llamaConnection {
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
        std::string_view const& systemPrompt, 
        std::string_view const& userPrompt, 
        std::string_view const& imageB64Blob
    ) {
        std::string sys_prompt = systemPrompt.empty() ? m_systemPrompt : std::string(systemPrompt);

        m_jsonRequest["messages"] = nlohmann::json::array({
            { {"role", "system"}, { "content", sys_prompt } },
            { {"role", "user"  }, { "content", {
                {{"type", "text"}, {"text", std::string(userPrompt) }},
                {{"type", "image_url"}, {"image_url", {{ "url", "data:image/jpeg;base64," + std::string(imageB64Blob) }}}}
            }}}
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