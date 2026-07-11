#include "llamaclient.hpp"
#include <util2/C/marker5.h>


void llamaClient::create(const std::string& host, uint16_t port) {
    mk_host    = host;
    mk_Headers = { {"Origin", "http://" + host} };
    m_cli      = std::make_unique<httplib::Client>(host, port);
    m_pool.create(2);
    return;
}

void llamaClient::destroy() {
    m_pool.destroy();
    m_cli.reset();
    return;
}

void llamaClient::submit(
    nlohmann::json const&  payload, 
    httpRequestCallback const& callback
) {
    if(!m_cli) { // Prevent segfault if not initialized 
        return;
    }

    std::string fetchFormattedDataNow = payload.dump();
    m_pool.enqueue([this, content = std::move(fetchFormattedDataNow), callback]() {
        markstr("submit_internal");
        auto res = m_cli->Post(mk_contentEndpoint, mk_Headers, content, mk_contentType);
        if(callback != nullptr) {
            markstr("submit_callback");
            callback(res);
        }
    });
}

[[nodiscard]] OptionalHttpRequestFuture llamaClient::submit(const nlohmann::json& payload) 
{
    if(!m_cli) return {}; // Need proper error handling here based on your future usage
    
    std::string fetchFormattedDataNow = payload.dump();
    return std::async(std::launch::async, [this, content = std::move(fetchFormattedDataNow)]() {
        return m_cli->Post(mk_contentEndpoint, mk_Headers, content, mk_contentType);
    });
}