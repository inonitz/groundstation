/* record_field.h -- a typed field of a span or an event: a name, a type and a value. The
 * name is a string literal that lives for the whole process; the writer prints it. No
 * table, no id (recorder.md section 2.1) */
#ifndef __HARDEN2_RECORD_FIELD_H__
#define __HARDEN2_RECORD_FIELD_H__

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef const char* FieldName;   /* a string literal; never freed */
typedef uint8_t  FieldCount;
typedef uint16_t TextLength;

/* kRecordMaxRecordBytes: the whole record, 8 KiB (RCD36); the largest record measured
 * is 5849 bytes. kRecordMaxFields: the caller's fields plus the recorder's one, "cut" */
enum {
	kRecordMaxCallerFields = 31,
	kRecordMaxFields = kRecordMaxCallerFields + 1,
	kRecordMaxRecordBytes = 8192
};

/* the recorder's own field, added only when a text was cut: the bytes lost (RCD37) */
#define FIELD_NAME_CUT  "cut"

_Static_assert(kRecordMaxFields <= 255, "FieldCount is a byte");
_Static_assert(kRecordMaxRecordBytes <= 65535, "RecordBytes is 16 bits");

typedef enum {
	FIELD_INT,
	FIELD_FLOAT,
	FIELD_BOOL,
	FIELD_TEXT
} FieldType;

/* m_bytes: the caller's, during the call only; copied into the record */
typedef struct {
	const char* m_bytes;
	TextLength  m_length;
} TextValue;

typedef union {
	int64_t   m_int;
	double    m_float;
	bool      m_bool;
	TextValue m_text;
} FieldValue;

typedef struct {
	FieldName  m_name;
	FieldType  m_type;
	FieldValue m_value;
} RecordField;

/* what every record call returns. DROPPED: a full queue or pool, STOPPING or STOPPED, a
 * frame under the reserve; INVALID_ARG: too many fields, a wrong frame size, format or
 * name. DROPPED and INVALID_ARG are counted; the other three results are not */
typedef enum {
	RECORD_OK,
	RECORD_DROPPED,
	RECORD_INVALID_ARG,
	RECORD_NO_FRAME_POOLS,
	RECORD_NOT_CREATED,
	RECORD_NOT_REGISTERED   /* the calling thread never registered; counted nowhere */
} RecordResult;

/* the field makers, for a C helper that reads as a sentence: a status out, a destination
 * in, the destination unchanged on false; the helper then stops before any record call.
 * In Python a maker returns the field or None. The hot path passes tuples (section 2.1) */
bool FieldInt(RecordField* out, FieldName name, int64_t value);
bool FieldFloat(RecordField* out, FieldName name, double value);
bool FieldBool(RecordField* out, FieldName name, bool value);
bool FieldText(RecordField* out, FieldName name, const char* bytes, TextLength length);

#endif
