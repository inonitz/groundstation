/* monotonic_clock.h -- the one time source of every record and every deadline:
 * CLOCK_MONOTONIC in nanoseconds; it never jumps and never goes back; every process on
 * the machine reads the same one. In Python: time.monotonic_ns() */
#ifndef __HARDEN2_UTIL_MONOTONIC_CLOCK_H__
#define __HARDEN2_UTIL_MONOTONIC_CLOCK_H__

#include <stdint.h>

typedef uint64_t MonotonicNs;
typedef uint64_t DurationNs;

MonotonicNs MonotonicNow(void);

#endif
