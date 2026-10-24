/* fixed_text.h -- a text of a fixed size as a named type, so a field carries its meaning:
 * DEFINE_FIXED_TEXT(PathText, 256) makes typedef struct { char m_text[256]; } PathText */
#ifndef __HARDEN2_UTIL_FIXED_TEXT_H__
#define __HARDEN2_UTIL_FIXED_TEXT_H__

#define DEFINE_FIXED_TEXT(Name, bytes) \
	typedef struct {                   \
		char m_text[bytes];            \
	} Name

#endif
