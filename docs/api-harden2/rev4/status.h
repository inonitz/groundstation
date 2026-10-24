/*
 * status.h -- harden2 API rev4 DRAFT (2026-10-02). The status rows (runtime/status.py).
 * Each part that can be up or down OWNS one row and is the only writer of it. The
 * status pane asks every part for its row. Nothing here is hidden: this header exists
 * for the owner to read the internals and the intent (owner HDR3).
 *  */
#ifndef __HARDEN2_API_STATUS_H__
#define __HARDEN2_API_STATUS_H__
#include "util.h"

/*
 * @STATE_DOWN:
 *     stopped on purpose
 */
typedef enum {
	STATE_STARTING,
	STATE_UP,
	STATE_RECOVERING,
	STATE_WAITING,
	STATE_FAILED,
	STATE_DOWN
} SysState;

/* what the pane shows for one part */
/*
 * @name:
 *     "gemma", "sam3", "dji app", "video", ...
 * @detail:
 *     the reason
 */
typedef struct {
	const char* name;
	SysState    state;
	const char* detail;
} StatusRow;

/* One row. No lock: its owner replaces the whole (state, detail) pair in ONE atomic
 *     step, so the screen never reads a state with another state's detail. */
/*
 * @current:
 *     ATOMIC pointer to the row in force
 */
typedef struct Status {
	const char* name;
	StatusRow*  current;
} Status;

Status* StatusCreate(const char* name);   /* starts STARTING */
void StatusSet(Status* s, SysState state, const char* detail);   /* prints each change */
StatusRow StatusGet(const Status* s);
/* The board is only a LIST of the rows, in the order the pane shows them. It owns no
 * row. */
typedef struct StatusBoard {
	Status** rows;
	uint32_t nRows;
} StatusBoard;

StatusBoard* StatusBoardCreate(Status** rows, uint32_t n);
uint32_t     StatusBoardSnapshot(const StatusBoard* b, StatusRow* out, uint32_t cap);
#endif
