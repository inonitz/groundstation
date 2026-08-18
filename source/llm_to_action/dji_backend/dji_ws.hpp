#pragma once
/*
    Opaque WebSocket client API for the DJI stick stream (WS /c/ws/sticks).

    TWO interchangeable implementations with an IDENTICAL surface. Selection is a
    compile-time typedef -- no virtual, matching the tree's tagged-dispatch style:

      RawWsClient  -- a hand-rolled RFC6455 client over a raw POSIX socket. Zero
                      third-party deps, exception-free, opaque Impl in
                      dji_ws_raw.cpp. Validates the handshake accept-key, sets
                      TCP_NODELAY, guards every op with a timeout, masks per spec,
                      and services inbound control frames (auto-PONG, honours CLOSE).
      WsppWsClient -- websocketpp + standalone Asio, opaque Impl in dji_ws_wspp.cpp.
                      The production-hardened reference to measure the raw one against.

    DjiBackend refers to `DjiWsClient` (RawWsClient by default; -DDJI_WS_WEBSOCKETPP
    flips it to WsppWsClient). The head-to-head test (test/dji_ws_test.cpp)
    instantiates BOTH by name and drives each against the mock.

    Contract (both clients):
      - connect(): resolve host, open TCP, do the WS upgrade. Blocking, bounded by
        timeoutMs. Returns false on any failure; leaves the client closed.
      - send_text(): frame + send one text message; also pumps inbound control
        frames. Returns false once the connection is gone (caller reconnects).
      - connected(): cheap liveness check. close(): idempotent teardown.
      No method throws.
*/
#include <memory>
#include <cstddef>
#include <util2/C/base_type.h>


class RawWsClient {
public:
    RawWsClient();
    ~RawWsClient();
    RawWsClient(const RawWsClient&)            = delete;
    RawWsClient& operator=(const RawWsClient&) = delete;

    bool connect(const char* host, u16 port, const char* path, u32 timeoutMs);
    bool send_text(const char* data, size_t len);
    bool connected() const;
    void close();
    static const char* name() { return "raw-rfc6455"; }

private:
    struct Impl;
    std::unique_ptr<Impl> m_impl;
};


class WsppWsClient {
public:
    WsppWsClient();
    ~WsppWsClient();
    WsppWsClient(const WsppWsClient&)            = delete;
    WsppWsClient& operator=(const WsppWsClient&) = delete;

    bool connect(const char* host, u16 port, const char* path, u32 timeoutMs);
    bool send_text(const char* data, size_t len);
    bool connected() const;
    void close();
    static const char* name() { return "websocketpp"; }

private:
    struct Impl;
    std::unique_ptr<Impl> m_impl;
};


#if defined(DJI_WS_WEBSOCKETPP)
using DjiWsClient = WsppWsClient;
#else
using DjiWsClient = RawWsClient;
#endif
