/* phone_mock.h -- the mock of the phone app: its process and its contract */
#ifndef __HARDEN2_PHONE_MOCK_H__
#define __HARDEN2_PHONE_MOCK_H__

#include "runtime.h"

/* the mock: python3 tools/dji_mock/mock_apiserver.py 127.0.0.1 <config's mock port>. It
 * binds 127.0.0.1 only; it serves the phone's routes; an unreadable body answers 200
 * "ok": false, as the phone does; SIGINT closes every open connection and exits within
 * 1 s */

/* the app's supervisor starts it when config's CONTROL is "mock" (the owner,
 * 2026-10-18), from this pure function of config and the log folder: env
 * MOCK_CMD_LOG=<logDir>/mock_commands.log, an addition (RUN15); GET /status/ as the
 * probe, 25 s; SIGINT, no retry, 10 s; BUDGET_SPENT_DIE; <logDir>/proc-mock.log */
ProcessSpec PhoneMockProcessSpec(const char* logDir);

#define PHONE_MOCK_READY_TIMEOUT_NS  UINT64_C(25000000000)

#endif
