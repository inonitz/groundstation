/* statistics.h -- program statistics: a struct of named RecordCount counters, one per
 * field, walked as an array for the arithmetic. One actor writes its own statistics;
 * where another thread reads them, they sit under a lock and are copied whole */
#ifndef __HARDEN2_UTIL_STATISTICS_H__
#define __HARDEN2_UTIL_STATISTICS_H__

#include <stdbool.h>
#include <stddef.h>

#include "common_names.h"

/* the number of counters of a statistics struct: every field is a RecordCount */
#define STATISTICS_COUNTERS(Type)  (sizeof(Type) / sizeof(RecordCount))

void StatisticsAdd(RecordCount* dst, const RecordCount* src, size_t counters);        /* dst += src */
void StatisticsSubtract(RecordCount* dst, const RecordCount* src, size_t counters);   /* dst -= src */
bool StatisticsAny(const RecordCount* s, size_t counters);   /* true when any counter is non-zero */

#endif
