#pragma once
/*
    target_tracker.hpp -- ROS-free, header-only multi-object tracker that gives every
    detection a STABLE tag (track id) frame to frame, plus a place to record the VLM's
    "this is the target" judgment (metadata) and, later, an appearance embedding.

    Why this exists: PerceptionSnapshot.dets[] is re-sorted every frame by detection
    confidence (NMS order), and TargetDetection carries no id. So "the 1st box" or even
    "a person" is not a stable target. This layer keeps a small memory of seen objects
    ("the bank") and matches each new frame's boxes against it, so the same real object
    keeps the same tag across frames and through brief dropouts.

    Identity source (v1) is GEOMETRY only -- IoU + centroid closeness. That is the
    reliable floor and is what SITL needs (every sim actor is the same mesh, so only
    position separates them). An appearance-embedding term is reserved on each track and
    fused in later behind a flag (see kEmbeddingDim / cosineSim + the score seam in
    pairCost); it is NOT populated by v1.

    Pure math, no ROS/OpenCV -- unit-testable with a standalone g++ run, same philosophy
    as detection_query.hpp / frame_convert.hpp. See test/target_tracker_test.cpp.
*/
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <util2/C/base_type.h>
#include <vision/perception_types.hpp>   /* TargetDetection / PerceptionSnapshot / kMaxDetections */

/* Bank capacity: >= kMaxDetections so all live boxes plus a few coasting ones fit. */
static constexpr u32 kMaxTracks    = 32u;
/* Reserved appearance-embedding width (OSNet-class ReID = 512). Unused by v1 geometry. */
static constexpr u32 kEmbeddingDim = 512u;

/* One remembered object. `id` is assigned once and never changes; `misses` is the buffer
   (frames since last matched) that lets a brief blink survive without losing the tag. */
struct Track {
    i32  id{-1};
    /* last box (px) + its center, kept for IoU/centroid matching. */
    i32  xmin{0}, ymin{0}, xmax{0}, ymax{0};
    f32  cx{0.0f}, cy{0.0f};
    FixedStringType label{"\0"};
    u32  hits{0};
    u32  misses{0};
    u64  last_seen_us{0};
    bool alive{false};
    /* metadata: the VLM's decision, carried along with the identity. */
    bool confirmed_target{false};
    FixedStringType attribute{"\0"};      /* e.g. "has_hat"; set when the VLM confirms.  */
    /* reserved appearance embedding (populated only when the flag-gated ReID path is on). */
    f32  embedding[kEmbeddingDim]{};
    bool has_embedding{false};
};

struct TargetTracker {
    Track tracks[kMaxTracks];
    u32   count{0};      /* number of slots ever used (compacted view: [0,count) may hold dead). */
    i32   nextId{0};     /* monotonic id source; retired ids are never reused.                    */
};

struct TrackerParams {
    f32 iouGate{0.3f};        /* >= this IoU associates a box to a track.                        */
    f32 distGatePx{80.0f};    /* OR centroid distance <= this (px) associates.                   */
    u32 maxAgeFrames{5u};     /* coast this many unmatched frames before a track is retired.     */
};

/* One id per detection this frame, index-aligned to snap.dets[]. id<0 never happens for a
   valid detection (every box gets a tag). */
struct FrameTrackIds {
    i32 id[PerceptionSnapshot::kMaxDetections];
    u32 count{0};
};

/* A snapshot plus its per-detection stable ids, published together so a reader gets both with
   one atomic load and matched lifetimes. `ids` is index-aligned to `snap.dets[]`. */
struct TrackedSnapshot {
    PerceptionSnapshot snap;
    FrameTrackIds      ids;
};

/* ---- pure geometry helpers ---------------------------------------------------------- */

static inline f32 trackerBoxIoU(i32 axmin, i32 aymin, i32 axmax, i32 aymax,
                                i32 bxmin, i32 bymin, i32 bxmax, i32 bymax) {
    i32 ix0 = axmin > bxmin ? axmin : bxmin;
    i32 iy0 = aymin > bymin ? aymin : bymin;
    i32 ix1 = axmax < bxmax ? axmax : bxmax;
    i32 iy1 = aymax < bymax ? aymax : bymax;
    i32 iw  = ix1 - ix0;
    i32 ih  = iy1 - iy0;
    if (iw <= 0 || ih <= 0) return 0.0f;
    f32 inter = static_cast<f32>(iw) * static_cast<f32>(ih);
    f32 aArea = static_cast<f32>(axmax - axmin) * static_cast<f32>(aymax - aymin);
    f32 bArea = static_cast<f32>(bxmax - bxmin) * static_cast<f32>(bymax - bymin);
    f32 uni   = aArea + bArea - inter;
    return (uni > 0.0f) ? (inter / uni) : 0.0f;
}

/* Cosine similarity of two embeddings (reserved for the flag-gated ReID path; exposed now
   so the metadata/re-ID tests can exercise it with synthetic vectors). */
static inline f32 cosineSim(f32 const* a, f32 const* b, u32 dim) {
    f32 dot = 0.0f, na = 0.0f, nb = 0.0f;
    for (u32 i = 0; i < dim; ++i) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
    if (na <= 0.0f || nb <= 0.0f) return 0.0f;
    return dot / (std::sqrt(na) * std::sqrt(nb));
}

/* Association cost for a (detection, track) pair. Lower = better. Returns a large sentinel
   when the pair is NOT allowed to match (label mismatch, or outside both geometry gates).
   THIS is the pluggable score seam: v1 is geometry only; the appearance term (cosine of the
   embeddings) is added here when the ReID path is enabled. */
constexpr f32 kTrackerNoMatch = 1.0e9f;
static inline f32 trackerPairCost(Track const& t, TargetDetection const& d,
                                  f32 dcx, f32 dcy, TrackerParams const& p) {
    if (std::strcmp(t.label, d.label) != 0) return kTrackerNoMatch;   /* labels must agree.   */
    f32 iou = trackerBoxIoU(t.xmin, t.ymin, t.xmax, t.ymax,
                            d.bbox_xmin, d.bbox_ymin, d.bbox_xmax, d.bbox_ymax);
    f32 dx  = t.cx - dcx, dy = t.cy - dcy;
    f32 dist = std::sqrt(dx * dx + dy * dy);
    bool gated = (iou >= p.iouGate) || (dist <= p.distGatePx);
    if (!gated) return kTrackerNoMatch;
    /* Cost blends "not overlapping" and "far apart", both in [0,1]-ish scale. IoU dominates
       when boxes overlap; centroid distance carries fast movers that barely overlap. */
    f32 distNorm = dist / (p.distGatePx > 0.0f ? p.distGatePx : 1.0f);
    return (1.0f - iou) + 0.5f * distNorm;
}

/* ---- the per-frame update (the whole tracker) --------------------------------------- */

struct TrackerPair { f32 cost; u32 det; u32 trk; };

/* Match this frame's boxes to the bank, assign/refresh/retire tags, and return the id for
   each detection (index-aligned to snap.dets[]). Greedy lowest-cost-first assignment --
   fine at N<=16 boxes x 32 tracks. Steps mirror the plan:
     1. score every allowed (box, track) pair,
     2. greedily lock best pairs (each box and track used once),
     3. matched -> refresh + reset miss counter; unmatched box -> new tag;
        unmatched track -> miss++ and retire past maxAgeFrames. */
static inline FrameTrackIds trackerUpdate(TargetTracker& st, PerceptionSnapshot const& snap,
                                          u64 now_us, TrackerParams const& p) {
    FrameTrackIds out;
    u32 n = (snap.valid ? snap.count : 0u);
    if (n > PerceptionSnapshot::kMaxDetections) n = PerceptionSnapshot::kMaxDetections;
    out.count = n;
    for (u32 i = 0; i < n; ++i) out.id[i] = -1;

    /* Precompute detection centers. */
    f32 dcx[PerceptionSnapshot::kMaxDetections];
    f32 dcy[PerceptionSnapshot::kMaxDetections];
    for (u32 i = 0; i < n; ++i) {
        dcx[i] = 0.5f * static_cast<f32>(snap.dets[i].bbox_xmin + snap.dets[i].bbox_xmax);
        dcy[i] = 0.5f * static_cast<f32>(snap.dets[i].bbox_ymin + snap.dets[i].bbox_ymax);
    }

    /* 1. all allowed (det, track) pairs. */
    TrackerPair pairs[PerceptionSnapshot::kMaxDetections * kMaxTracks];
    u32 nPairs = 0;
    for (u32 di = 0; di < n; ++di) {
        for (u32 ti = 0; ti < st.count && ti < kMaxTracks; ++ti) {
            if (!st.tracks[ti].alive) continue;
            f32 c = trackerPairCost(st.tracks[ti], snap.dets[di], dcx[di], dcy[di], p);
            if (c >= kTrackerNoMatch) continue;
            pairs[nPairs++] = { c, di, ti };
        }
    }

    /* 2. greedy: best cost first, each det and track claimed once. */
    std::sort(pairs, pairs + nPairs, [](TrackerPair const& a, TrackerPair const& b) {
        return a.cost < b.cost;
    });
    bool detUsed[PerceptionSnapshot::kMaxDetections] = { false };
    bool trkUsed[kMaxTracks]                          = { false };
    for (u32 k = 0; k < nPairs; ++k) {
        u32 di = pairs[k].det, ti = pairs[k].trk;
        if (detUsed[di] || trkUsed[ti]) continue;
        detUsed[di] = true; trkUsed[ti] = true;
        Track& t = st.tracks[ti];
        t.xmin = snap.dets[di].bbox_xmin; t.ymin = snap.dets[di].bbox_ymin;
        t.xmax = snap.dets[di].bbox_xmax; t.ymax = snap.dets[di].bbox_ymax;
        t.cx = dcx[di]; t.cy = dcy[di];
        std::snprintf(t.label, sizeof(FixedStringType), "%s", snap.dets[di].label);
        t.hits += 1; t.misses = 0; t.last_seen_us = now_us; t.alive = true;
        out.id[di] = t.id;   /* metadata (confirmed_target/attribute/embedding) rides along. */
    }

    /* 3a. unmatched detections -> brand-new tracks (only place an id is minted). */
    for (u32 di = 0; di < n; ++di) {
        if (detUsed[di]) continue;
        /* find a dead slot, or append. */
        u32 slot = kMaxTracks;
        for (u32 ti = 0; ti < st.count && ti < kMaxTracks; ++ti)
            if (!st.tracks[ti].alive) { slot = ti; break; }
        if (slot == kMaxTracks && st.count < kMaxTracks) slot = st.count++;
        if (slot == kMaxTracks) continue;   /* bank full of live tracks: drop (N<=16<32, rare). */
        Track& t = st.tracks[slot];
        t = Track{};
        t.id = st.nextId++;
        t.xmin = snap.dets[di].bbox_xmin; t.ymin = snap.dets[di].bbox_ymin;
        t.xmax = snap.dets[di].bbox_xmax; t.ymax = snap.dets[di].bbox_ymax;
        t.cx = dcx[di]; t.cy = dcy[di];
        std::snprintf(t.label, sizeof(FixedStringType), "%s", snap.dets[di].label);
        t.hits = 1; t.misses = 0; t.last_seen_us = now_us; t.alive = true;
        out.id[di] = t.id;
    }

    /* 3b. unmatched tracks -> age; retire past the coast window. */
    for (u32 ti = 0; ti < st.count && ti < kMaxTracks; ++ti) {
        Track& t = st.tracks[ti];
        if (!t.alive || trkUsed[ti]) continue;
        t.misses += 1;
        if (t.misses > p.maxAgeFrames) t.alive = false;   /* tag retired; id never reused.   */
    }
    return out;
}

/* ---- metadata helpers (used by the verbs + tests) ----------------------------------- */

/* Set the VLM's confirmation on a track by id. attribute may be nullptr/"" for a bare flag. */
static inline bool trackerSetConfirmed(TargetTracker& st, i32 id, char const* attribute) {
    for (u32 ti = 0; ti < st.count && ti < kMaxTracks; ++ti) {
        if (st.tracks[ti].alive && st.tracks[ti].id == id) {
            st.tracks[ti].confirmed_target = true;
            if (attribute) std::snprintf(st.tracks[ti].attribute, sizeof(FixedStringType), "%s", attribute);
            return true;
        }
    }
    return false;
}

/* The live track carrying id, or nullptr. */
static inline Track const* trackerFindById(TargetTracker const& st, i32 id) {
    if (id < 0) return nullptr;
    for (u32 ti = 0; ti < st.count && ti < kMaxTracks; ++ti)
        if (st.tracks[ti].alive && st.tracks[ti].id == id) return &st.tracks[ti];
    return nullptr;
}

/* Recover by unique attribute: the single live track carrying `attribute`, or nullptr if
   none OR more than one match (ambiguity guard -- never auto-rebind an ambiguous attribute;
   defer to the VLM). This is the geometry-era recovery; the embedding path supersedes it
   when enabled. */
static inline Track const* trackerFindByAttribute(TargetTracker const& st, char const* attribute) {
    Track const* hit = nullptr;
    for (u32 ti = 0; ti < st.count && ti < kMaxTracks; ++ti) {
        Track const& t = st.tracks[ti];
        if (!t.alive || !t.confirmed_target) continue;
        if (std::strcmp(t.attribute, attribute) != 0) continue;
        if (hit != nullptr) return nullptr;   /* ambiguous -> refuse. */
        hit = &t;
    }
    return hit;
}
