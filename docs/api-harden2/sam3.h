/*
 * sam3.h -- harden2 API v2.5 (2026-09-29). Module sam3/: the SAM3 SERVICE (owner 1.8.1 + D2).
 * contract.py: the backend contract below (DetectStatus, detect, mask_for_box).
 * loader.py:   Sam3Load, the loader service: loads the backend on its own thread at start,
 *              then ONE warm-up pass on a blank camera-size frame before its row is UP (L1);
 *              its "sam3" row; detect answers DETECT_NOT_READY until it is loaded.
 * model.py:    the SAM3-nf4 model: boxes AND masks, nested boxes merged. A detect encodes the
 *              frame ONCE, then runs the text + detector step per concept (owner S1; the
 *              A/B: bench/perception/ab_shared_encoding.py, same boxes, 0.0 px).
 * Importing sam3/ loads no model: torch arrives with model.py, on the loader's thread (S3).
 * save_nf4.py: saves SAM3 ONCE in its nf4 form to config.SAM3_NF4_DIR (owner S7 c); the
 *              loader loads those ready weights (the install script runs it when missing).
 * The vision system (perception.h) uses it; so do the benchmarks.
 */
#ifndef __HARDEN2_API_SAM3_H__
#define __HARDEN2_API_SAM3_H__
#include "runtime.h"
#include "video.h"

/* ---- the vision backend (SAM3 today; SAM3.1 / EOVSAM later drop in here) ---- */
typedef enum { DETECT_OK, DETECT_NOT_READY } DetectStatus;   /* "no hits" is DETECT_OK, n=0 */
typedef struct { float x0, y0, x1, y1, conf; char label[32]; } Box;
typedef struct { uint32_t width, height; uint8_t* bits; } Mask;   /* 1 byte per pixel        */
typedef struct {
	const char* name;                     /* config SCENE_SEG: "sam3"; unknown name -> die    */
	const char* modelDir;
	const char* precision;                /* "nf4", fixed at load                             */
} BackendConfig;
typedef struct Sam3 Sam3;               /* the backend loader: a SERVICE             */
Sam3*        Sam3Load(const BackendConfig* cfg);   /* async; fail -> die             */
uint32_t     Sam3Status(Sam3* s, StatusRow* rows, uint32_t cap);   /* its "sam3" row */
DetectStatus VisionDetect(const VideoFrame* f, const char* phrase, float floor, uint32_t topk,
	Box* hits, uint32_t cap, uint32_t* n);   /* nested boxes of one object already merged     */
bool         VisionMaskFor(const VideoFrame* f, const Box* box, Mask* out);  /* last detect */
/* GPU out of memory in a forward -> die (owner: no retry for now). */

#endif /* __HARDEN2_API_SAM3_H__ */
