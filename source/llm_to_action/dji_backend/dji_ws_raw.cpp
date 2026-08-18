/*
    RawWsClient -- a hand-rolled RFC6455 WebSocket client over a raw POSIX socket.
    Zero third-party dependencies; exception-free (every path returns bool). This
    is the deliberately-minimal alternative to websocketpp: the DJI stick stream
    only ever sends small masked text frames and ignores the server's echo, so the
    whole client is a handshake + a frame writer + a small inbound control pump.

    Robustness choices (the reasons it is safe to fly, not just short):
      - getaddrinfo: hostnames AND dotted IPs; walks every result.
      - non-blocking connect + select(): connect() cannot hang past timeoutMs.
      - TCP_NODELAY: 18 Hz tiny control frames must not sit in Nagle's buffer.
      - SO_SND/RCVTIMEO: no send() or recv() can block a control loop indefinitely.
      - handshake ACCEPT-KEY validation (SHA-1 + base64): proves we reached a real
        RFC6455 endpoint, not a bare TCP listener that happened to accept.
      - partial-write-safe framing with EINTR retry and mandatory client masking.
      - inbound pump: drains echoes so the RX buffer never stalls, replies PONG to
        PING (or the peer eventually drops us), and flips to closed on CLOSE/EOF.

    All wire logic lives on RawWsClient::Impl so it has access to the private
    state; the public methods just forward.
*/
#include "dji_backend/dji_ws.hpp"

#include <sys/socket.h>
#include <sys/select.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <cerrno>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <chrono>
#include <string>
#include <vector>
#include <random>


namespace {

/* ---- SHA-1 (RFC 3174) -- only for the WS handshake accept-key check. -------- */
struct Sha1 {
    uint32_t h[5];
    uint64_t bits;
    uint8_t  buf[64];
    size_t   n;

    void init() {
        h[0]=0x67452301u; h[1]=0xEFCDAB89u; h[2]=0x98BADCFEu; h[3]=0x10325476u; h[4]=0xC3D2E1F0u;
        bits=0; n=0;
    }
    static uint32_t rol(uint32_t x, unsigned c) { return (x<<c)|(x>>(32u-c)); }
    void block(const uint8_t* p) {
        uint32_t w[80];
        for (int i=0;i<16;i++)
            w[i]=(uint32_t(p[i*4])<<24)|(uint32_t(p[i*4+1])<<16)|(uint32_t(p[i*4+2])<<8)|uint32_t(p[i*4+3]);
        for (int i=16;i<80;i++) w[i]=rol(w[i-3]^w[i-8]^w[i-14]^w[i-16],1);
        uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4];
        for (int i=0;i<80;i++) {
            uint32_t f,k;
            if      (i<20) { f=(b&c)|((~b)&d);        k=0x5A827999u; }
            else if (i<40) { f=b^c^d;                 k=0x6ED9EBA1u; }
            else if (i<60) { f=(b&c)|(b&d)|(c&d);     k=0x8F1BBCDCu; }
            else           { f=b^c^d;                 k=0xCA62C1D6u; }
            uint32_t t=rol(a,5)+f+e+k+w[i];
            e=d; d=c; c=rol(b,30); b=a; a=t;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e;
    }
    void update(const uint8_t* p, size_t l) {
        bits += uint64_t(l)*8u;
        while (l) { size_t take=64-n; if (take>l) take=l; std::memcpy(buf+n,p,take); n+=take; p+=take; l-=take; if (n==64){ block(buf); n=0; } }
    }
    void finish(uint8_t out[20]) {
        uint64_t total=bits;                   /* captured before padding mutates bits */
        uint8_t one=0x80; update(&one,1);
        uint8_t zero=0;  while (n!=56) update(&zero,1);
        uint8_t lb[8]; for (int i=0;i<8;i++) lb[i]=uint8_t(total>>(56-i*8));
        update(lb,8);
        for (int i=0;i<5;i++) { out[i*4]=uint8_t(h[i]>>24); out[i*4+1]=uint8_t(h[i]>>16); out[i*4+2]=uint8_t(h[i]>>8); out[i*4+3]=uint8_t(h[i]); }
    }
};

std::string b64(const uint8_t* p, size_t n) {
    static const char* T="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string o; o.reserve(((n+2)/3)*4);
    size_t i=0;
    for (; i+3<=n; i+=3) {
        uint32_t v=(uint32_t(p[i])<<16)|(uint32_t(p[i+1])<<8)|uint32_t(p[i+2]);
        o+=T[(v>>18)&63]; o+=T[(v>>12)&63]; o+=T[(v>>6)&63]; o+=T[v&63];
    }
    size_t rem=n-i;
    if (rem==1) { uint32_t v=uint32_t(p[i])<<16; o+=T[(v>>18)&63]; o+=T[(v>>12)&63]; o+='='; o+='='; }
    else if (rem==2) { uint32_t v=(uint32_t(p[i])<<16)|(uint32_t(p[i+1])<<8); o+=T[(v>>18)&63]; o+=T[(v>>12)&63]; o+=T[(v>>6)&63]; o+='='; }
    return o;
}

uint64_t now_ms() {
    using namespace std::chrono;
    return uint64_t(duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count());
}

void make_mask(uint8_t m[4]) {
    static thread_local std::mt19937 rng{std::random_device{}()};
    uint32_t r=rng(); m[0]=uint8_t(r); m[1]=uint8_t(r>>8); m[2]=uint8_t(r>>16); m[3]=uint8_t(r>>24);
}

void set_timeouts(int fd, u32 ms) {
    timeval tv; tv.tv_sec=time_t(ms/1000); tv.tv_usec=suseconds_t((ms%1000)*1000);
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    ::setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}

bool connect_timeout(int fd, const sockaddr* addr, socklen_t len, u32 ms) {
    int fl=::fcntl(fd,F_GETFL,0);
    ::fcntl(fd,F_SETFL,fl|O_NONBLOCK);
    int r=::connect(fd,addr,len);
    if (r!=0) {
        if (errno!=EINPROGRESS) return false;
        fd_set wset; FD_ZERO(&wset); FD_SET(fd,&wset);
        timeval tv; tv.tv_sec=time_t(ms/1000); tv.tv_usec=suseconds_t((ms%1000)*1000);
        if (::select(fd+1,nullptr,&wset,nullptr,&tv)<=0) return false;      /* timeout/err */
        int soerr=0; socklen_t sl=sizeof(soerr);
        if (::getsockopt(fd,SOL_SOCKET,SO_ERROR,&soerr,&sl)<0 || soerr!=0) return false;
    }
    ::fcntl(fd,F_SETFL,fl);                                                 /* back to blocking */
    return true;
}

bool writeall(int fd, const uint8_t* p, size_t n) {
    size_t off=0;
    while (off<n) {
        ssize_t w=::send(fd,p+off,n-off,MSG_NOSIGNAL);
        if (w>0) { off+=size_t(w); continue; }
        if (w<0 && errno==EINTR) continue;
        return false;                          /* EAGAIN(timeout) / EPIPE / ... */
    }
    return true;
}

std::string header_value(const std::string& resp, const char* nameLower) {
    std::string low(resp.size(),'\0');
    for (size_t i=0;i<resp.size();i++) low[i]=char(std::tolower((unsigned char)resp[i]));
    std::string key=std::string("\r\n")+nameLower+":";
    size_t p=low.find(key);
    if (p==std::string::npos) return "";
    p+=key.size();
    size_t e=resp.find("\r\n",p);
    if (e==std::string::npos) return "";
    while (p<e && (resp[p]==' '||resp[p]=='\t')) p++;
    size_t end=e; while (end>p && (resp[end-1]==' '||resp[end-1]=='\t')) end--;
    return resp.substr(p,end-p);
}

} /* anonymous namespace */


/* ---- The client state + all wire logic ------------------------------------ */
struct RawWsClient::Impl {
    int                  fd{-1};
    bool                 closing{false};
    std::vector<uint8_t> rx;        /* partial-frame accumulator */

    bool connect(const char* host, u16 port, const char* path, u32 timeoutMs);
    bool send_text(const char* data, size_t len);
    bool connected() const { return fd>=0 && !closing; }
    void close();

    /* helpers */
    bool handshake(const char* host, u16 port, const char* path, u32 timeoutMs);
    bool send_frame(uint8_t opcode, const uint8_t* payload, size_t len);
    void pump();                    /* drain RX, answer control frames */
    void parse_frames();
};


bool RawWsClient::Impl::connect(const char* host, u16 port, const char* path, u32 timeoutMs) {
    close();                                     /* idempotent: drop any prior socket */

    addrinfo hints; std::memset(&hints,0,sizeof(hints));
    hints.ai_family=AF_UNSPEC; hints.ai_socktype=SOCK_STREAM;
    char portstr[8]; std::snprintf(portstr,sizeof(portstr),"%u",unsigned(port));
    addrinfo* res=nullptr;
    if (::getaddrinfo(host,portstr,&hints,&res)!=0 || !res) return false;

    int sock=-1;
    for (addrinfo* ai=res; ai; ai=ai->ai_next) {
        sock=::socket(ai->ai_family,ai->ai_socktype,ai->ai_protocol);
        if (sock<0) continue;
        if (connect_timeout(sock,ai->ai_addr,socklen_t(ai->ai_addrlen),timeoutMs)) break;
        ::close(sock); sock=-1;
    }
    ::freeaddrinfo(res);
    if (sock<0) return false;

    int one=1; ::setsockopt(sock,IPPROTO_TCP,TCP_NODELAY,&one,sizeof(one));
    set_timeouts(sock,timeoutMs);
    fd=sock; closing=false; rx.clear();

    if (!handshake(host,port,path,timeoutMs)) { close(); return false; }
    return true;
}

bool RawWsClient::Impl::handshake(const char* host, u16 port, const char* path, u32 timeoutMs) {
    uint8_t rawkey[16];
    { std::random_device rd; for (int i=0;i<16;i++) rawkey[i]=uint8_t(rd()); }
    std::string key=b64(rawkey,16);

    char req[512];
    int rn=std::snprintf(req,sizeof(req),
        "GET %s HTTP/1.1\r\nHost: %s:%u\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n",
        path,host,unsigned(port),key.c_str());
    if (rn<=0 || rn>=int(sizeof(req))) return false;
    if (!writeall(fd,reinterpret_cast<const uint8_t*>(req),size_t(rn))) return false;

    std::string resp; resp.reserve(512);
    uint64_t deadline=now_ms()+timeoutMs;
    char b[512];
    while (resp.find("\r\n\r\n")==std::string::npos) {
        if (now_ms()>deadline) return false;
        ssize_t r=::recv(fd,b,sizeof(b),0);
        if (r>0)      { resp.append(b,size_t(r)); if (resp.size()>16384) return false; }
        else if (r<0 && errno==EINTR) continue;
        else          return false;              /* timeout / closed */
    }
    if (resp.compare(0,12,"HTTP/1.1 101")!=0 && resp.compare(0,12,"HTTP/1.0 101")!=0) return false;

    /* Accept = base64(sha1(clientKey + magic GUID)). Reject a wrong/absent value. */
    std::string magic=key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    Sha1 s; s.init(); s.update(reinterpret_cast<const uint8_t*>(magic.data()),magic.size());
    uint8_t dig[20]; s.finish(dig);
    if (header_value(resp,"sec-websocket-accept")!=b64(dig,20)) return false;

    /* Anything past the header terminator already belongs to the WS stream. */
    size_t hdr=resp.find("\r\n\r\n")+4;
    if (hdr<resp.size()) rx.insert(rx.end(),resp.begin()+long(hdr),resp.end());
    return true;
}

bool RawWsClient::Impl::send_frame(uint8_t opcode, const uint8_t* payload, size_t len) {
    if (fd<0) return false;
    /* Alloc-free for the common small frame: header(<=10) + mask(4) + payload. A
       FlightParam JSON is ~70 bytes, so the ~18 Hz stick hot path NEVER allocates
       -- unlike websocketpp, which heap-allocates a buffer per message sent. Only
       an implausibly large control payload falls back to the heap. */
    uint8_t  stackbuf[512];
    std::vector<uint8_t> heap;
    size_t   need = len + 14;
    uint8_t* f    = stackbuf;
    if (need > sizeof(stackbuf)) { heap.resize(need); f = heap.data(); }

    size_t k=0;
    f[k++]=uint8_t(0x80|opcode);                       /* FIN + opcode */
    uint8_t mask[4]; make_mask(mask);
    if (len<126)          f[k++]=uint8_t(0x80|len);
    else if (len<65536) { f[k++]=uint8_t(0x80|126); f[k++]=uint8_t(len>>8); f[k++]=uint8_t(len); }
    else                { f[k++]=uint8_t(0x80|127); for (int i=7;i>=0;i--) f[k++]=uint8_t(uint64_t(len)>>(i*8)); }
    f[k++]=mask[0]; f[k++]=mask[1]; f[k++]=mask[2]; f[k++]=mask[3];
    for (size_t i=0;i<len;i++) f[k++]=uint8_t(payload[i]^mask[i&3]);
    if (!writeall(fd,f,k)) { closing=true; return false; }
    return true;
}

bool RawWsClient::Impl::send_text(const char* data, size_t len) {
    if (fd<0 || closing) return false;
    if (!send_frame(0x1,reinterpret_cast<const uint8_t*>(data),len)) return false;
    pump();                                            /* service echoes / pings / close */
    return !closing;
}

void RawWsClient::Impl::pump() {
    uint8_t b[2048];
    for (;;) {
        ssize_t r=::recv(fd,b,sizeof(b),MSG_DONTWAIT);
        if (r>0)      { rx.insert(rx.end(),b,b+size_t(r)); if (rx.size()>(1u<<20)) rx.clear(); continue; }
        if (r==0)     { closing=true; break; }         /* peer closed */
        break;                                         /* EAGAIN (no data) or error */
    }
    parse_frames();
}

void RawWsClient::Impl::parse_frames() {
    size_t off=0;
    for (;;) {
        if (rx.size()-off<2) break;
        uint8_t b1=rx[off+1];
        bool     masked=(b1&0x80)!=0;
        uint64_t plen=b1&0x7Fu;
        size_t   hdr=2;
        if (plen==126) { if (rx.size()-off<4)  break; plen=(uint64_t(rx[off+2])<<8)|rx[off+3]; hdr=4; }
        else if (plen==127) { if (rx.size()-off<10) break; plen=0; for (int i=0;i<8;i++) plen=(plen<<8)|rx[off+2+size_t(i)]; hdr=10; }
        size_t masklen=masked?4:0;
        if (rx.size()-off < hdr+masklen+plen) break;   /* frame not fully arrived */

        uint8_t opcode=rx[off]&0x0F;
        const uint8_t* payload=&rx[off+hdr+masklen]; /* servers send unmasked */
        if      (opcode==0x8) { closing=true; }                       /* CLOSE  */
        else if (opcode==0x9) { send_frame(0xA,payload,size_t(plen)); } /* PING -> PONG */
        /* 0xA PONG and 0x1/0x2 echoes are ignored. */
        off += hdr+masklen+size_t(plen);
    }
    if (off>0) rx.erase(rx.begin(),rx.begin()+long(off));
}

void RawWsClient::Impl::close() {
    if (fd>=0) {
        uint8_t mask[4]; make_mask(mask);
        uint8_t f[6]={ 0x88, 0x80, mask[0],mask[1],mask[2],mask[3] };  /* CLOSE, empty, masked */
        writeall(fd,f,sizeof(f));
        ::shutdown(fd,SHUT_RDWR);
        ::close(fd);
        fd=-1;
    }
    rx.clear();
    closing=false;
}


/* ---- public forwarders ----------------------------------------------------- */
RawWsClient::RawWsClient() : m_impl(new Impl) {}
RawWsClient::~RawWsClient() { m_impl->close(); }
bool RawWsClient::connect(const char* host, u16 port, const char* path, u32 timeoutMs) { return m_impl->connect(host,port,path,timeoutMs); }
bool RawWsClient::send_text(const char* data, size_t len) { return m_impl->send_text(data,len); }
bool RawWsClient::connected() const { return m_impl->connected(); }
void RawWsClient::close() { m_impl->close(); }
