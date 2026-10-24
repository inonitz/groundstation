/* spsc_record_queue.h -- a bounded queue of records with ONE producer and ONE consumer;
 * full means the new record is dropped and counted. Python: a deque of tuples, bounded
 * by a count (150 ns a push). C: a ring of record slots and a byte area (section 2.1) */
#ifndef __HARDEN2_UTIL_SPSC_RECORD_QUEUE_H__
#define __HARDEN2_UTIL_SPSC_RECORD_QUEUE_H__

#include <stdalign.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "common_names.h"

typedef uint16_t RecordBytes;   /* one record's length */
typedef uint8_t  RecordKind;    /* the user's kinds */

/* ============================ 1. the contract ============================== */

typedef struct SpscRecordQueue SpscRecordQueue;

/* the two endpoints are distinct types, so a holder can only produce or only consume */
typedef struct {
	SpscRecordQueue* m_queue;
} SpscProducer;

typedef struct {
	SpscRecordQueue* m_queue;
} SpscConsumer;

/* false: the allocation failed; on true the two endpoints are filled, each for exactly
 * one thread. The queue holds at most maxRecords records of at most maxRecordBytes each */
bool SpscRecordQueueCreate(
	SpscRecordQueue* q,
	RecordCount maxRecords,
	RecordBytes maxRecordBytes,
	SpscProducer* producer,
	SpscConsumer* consumer
);
void SpscRecordQueueDestroy(SpscRecordQueue* q);

/* false: full; the record is dropped and counted by the caller */
bool SpscProducerPush(
	SpscProducer* p,
	RecordKind kind,
	const void* record,
	RecordBytes bytes
);
/* pushed and not yet popped */
RecordCount SpscProducerRecordsQueued(const SpscProducer* p);

/* the oldest record, without removing it: false when empty; the pointer stays valid
 * until Pop, which removes that one record */
bool SpscConsumerFront(
	SpscConsumer* c,
	RecordKind* kind,
	const void** record,
	RecordBytes* bytes
);
void SpscConsumerPop(SpscConsumer* c);

/* ============================ 2. the C storage ============================= */

typedef uint32_t RingPosition;   /* grows forever; the slot is the position masked by the count */
typedef uint32_t ByteOffset;

enum {
	kCacheLineBytes = 64,
	kRingBytesPerRecordExpected = 64
};

/* one slot per record: where its bytes are and what it is; the bytes live in the byte
 * area, written before the slot is published. m_reserved: zero */
typedef struct {
	ByteOffset  m_at;
	RecordBytes m_bytes;
	RecordKind  m_kind;
	uint8_t     m_reserved;
} RecordSlot;

/* two rings that move together, the slots and the byte area; a record that does not fit
 * before the end goes at 0. m_head is the producer's and m_tail the consumer's, each on
 * its own cache line; release stores, acquire loads. m_slotCount: a power of two */
struct SpscRecordQueue {
	RecordCount m_slotCount;
	RecordBytes m_maxRecordBytes;
	RecordSlot* m_slots;
	uint8_t*    m_bytes;
	ByteOffset  m_byteCapacity;
	alignas(kCacheLineBytes) _Atomic RingPosition m_head;
	alignas(kCacheLineBytes) _Atomic RingPosition m_tail;
};

#endif
