/* common_names.h -- the fixed-size names more than one module writes: a path, a
 * process, a thread */
#ifndef __HARDEN2_UTIL_COMMON_NAMES_H__
#define __HARDEN2_UTIL_COMMON_NAMES_H__

#include <stdint.h>

#include "fixed_text.h"

DEFINE_FIXED_TEXT(PathText, 256);
DEFINE_FIXED_TEXT(ProcessName, 32);
DEFINE_FIXED_TEXT(ThreadName, 32);

typedef uint32_t RecordCount;   /* records, in a queue or in a counter */
typedef uint32_t ThreadIdx;     /* an index into the producers table; "t" in the file */
typedef uint32_t ThreadCount;   /* a count of producers */

#endif
