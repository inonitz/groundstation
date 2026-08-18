/*
    WsppWsClient -- the DJI stick-stream WebSocket client built on websocketpp +
    standalone Asio. This is the production-hardened reference the hand-rolled
    RawWsClient is measured against (test/dji_ws_test.cpp runs both).

    websocketpp drives its own Asio io_context on a private thread; connect()
    blocks (bounded) on a condition variable until the open/fail handler fires.
    We use the error_code-returning overloads everywhere, so our own control flow
    never relies on exceptions (project rule) -- websocketpp's internal use of
    them is the library's business, and this TU is compiled with exceptions ON
    (the tree does not pass -fno-exceptions).

    ASIO_STANDALONE: no Boost. Defined here, before any Asio/websocketpp include.
    Access channels are silenced so the control loop's stdout stays clean.
*/
#ifndef ASIO_STANDALONE
#define ASIO_STANDALONE
#endif
#include <websocketpp/config/asio_no_tls_client.hpp>
#include <websocketpp/client.hpp>

#include "dji_backend/dji_ws.hpp"

#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <string>
#include <thread>


namespace {
using WsClient = websocketpp::client<websocketpp::config::asio_client>;
}


struct WsppWsClient::Impl {
    WsClient                     endpoint;
    std::thread                  runner;
    websocketpp::connection_hdl  hdl;

    std::mutex                   mtx;
    std::condition_variable      cv;
    bool                         resolved{false};   /* open or fail handler fired */
    std::atomic<bool>            open{false};

    bool connect(const char* host, u16 port, const char* path, u32 timeoutMs);
    bool send_text(const char* data, size_t len);
    bool connected() const { return open.load(std::memory_order_relaxed); }
    void close();
};


bool WsppWsClient::Impl::connect(const char* host, u16 port, const char* path, u32 timeoutMs) {
    close();                                        /* idempotent */

    endpoint.clear_access_channels(websocketpp::log::alevel::all);
    endpoint.clear_error_channels(websocketpp::log::elevel::all);

    websocketpp::lib::error_code ec;
    endpoint.init_asio(ec);
    if (ec) return false;
    endpoint.start_perpetual();                     /* keep io alive across idle */

    endpoint.set_open_handler([this](websocketpp::connection_hdl h){
        { std::lock_guard<std::mutex> lk(mtx); hdl=h; open.store(true,std::memory_order_relaxed); resolved=true; }
        cv.notify_all();
    });
    endpoint.set_fail_handler([this](websocketpp::connection_hdl){
        { std::lock_guard<std::mutex> lk(mtx); open.store(false,std::memory_order_relaxed); resolved=true; }
        cv.notify_all();
    });
    endpoint.set_close_handler([this](websocketpp::connection_hdl){
        open.store(false,std::memory_order_relaxed);
    });

    char uri[256];
    std::snprintf(uri,sizeof(uri),"ws://%s:%u%s",host,unsigned(port),path);
    WsClient::connection_ptr con=endpoint.get_connection(uri,ec);
    if (ec) return false;

    runner=std::thread([this]{ endpoint.run(); });
    endpoint.connect(con);

    std::unique_lock<std::mutex> lk(mtx);
    bool ok=cv.wait_for(lk,std::chrono::milliseconds(timeoutMs),[this]{ return resolved; });
    if (!ok || !open.load(std::memory_order_relaxed)) { lk.unlock(); close(); return false; }
    return true;
}

bool WsppWsClient::Impl::send_text(const char* data, size_t len) {
    if (!open.load(std::memory_order_relaxed)) return false;
    websocketpp::lib::error_code ec;
    endpoint.send(hdl, std::string(data,len), websocketpp::frame::opcode::text, ec);
    return !ec;
}

void WsppWsClient::Impl::close() {
    if (open.load(std::memory_order_relaxed)) {
        websocketpp::lib::error_code ec;
        endpoint.close(hdl, websocketpp::close::status::normal, "", ec);
    }
    open.store(false,std::memory_order_relaxed);
    endpoint.stop_perpetual();
    if (runner.joinable()) runner.join();            /* run() returns once no work remains */
    resolved=false;
}


/* ---- public forwarders ----------------------------------------------------- */
WsppWsClient::WsppWsClient() : m_impl(new Impl) {}
WsppWsClient::~WsppWsClient() { m_impl->close(); }
bool WsppWsClient::connect(const char* host, u16 port, const char* path, u32 timeoutMs) { return m_impl->connect(host,port,path,timeoutMs); }
bool WsppWsClient::send_text(const char* data, size_t len) { return m_impl->send_text(data,len); }
bool WsppWsClient::connected() const { return m_impl->connected(); }
void WsppWsClient::close() { m_impl->close(); }
