/* index_queue.h -- a bounded first-in first-out queue of indexes of a pool's items, safe
 * for any number of threads on either side: one lock, held for a few loads and stores.
 * In Python: a collections.deque under one threading.Lock (recorder.md section 2.4) */
#ifndef __HARDEN2_UTIL_INDEX_QUEUE_H__
#define __HARDEN2_UTIL_INDEX_QUEUE_H__

#include <stdbool.h>
#include <stdint.h>

typedef uint32_t ItemIndex;
typedef uint32_t ItemCount;

#define INDEX_NONE  UINT32_C(0xFFFFFFFF)

typedef struct OsLock OsLock;   /* the runtime's mutex (runtime_internal.h) */

/* the payload of an index is the user's own array; an index that is in no queue belongs
 * to the one thread that popped it. m_indexes: m_capacity entries, a ring under the lock */
typedef struct {
	OsLock*    m_lock;
	ItemIndex* m_indexes;
	ItemCount  m_capacity;
	ItemCount  m_head;
	ItemCount  m_count;
} IndexQueue;

/* false: the allocation failed */
bool IndexQueueCreate(IndexQueue* q, ItemCount capacity);
void IndexQueueDestroy(IndexQueue* q);

bool      IndexQueuePush(IndexQueue* q, ItemIndex index);   /* false: full */
ItemIndex IndexQueuePop(IndexQueue* q);   /* the oldest, removed; INDEX_NONE: empty */
/* the oldest, not removed; INDEX_NONE: empty. Push, Pop and Front each take the lock
 * inside; a caller that reads the item a Front names reads it a moment later, unlocked */
ItemIndex IndexQueueFront(IndexQueue* q);

#endif
