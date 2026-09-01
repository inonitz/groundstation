#pragma once
/*
    detectionByLabel -- ROS-free camera-intrinsics + pinhole back-projection from a
    PerceptionSnapshot detection to a body-FLU direction + metric range. Shared by
    APPROACH (block 5.1) today; ORBIT/SEARCH (block 1.1.6/1.1.7) will call the same
    query later and keep their own control/timeout policy (spec D3).

    Pure math, no ROS include -- unit-testable with a standalone g++ run
    (see test/detection_query_test.cpp), same philosophy as frame/frame_convert.hpp.

    Camera -> body-FLU convention (forward-facing camera, optical z forward, x right,
    y down): a pixel (u,v) back-projects to a camera-frame ray raw = {1, -camX, -camY}
    where camX=(u-cx)/fx, camY=(v-cy)/fy; dirFlu = normalize(raw). No odometry, no
    world frame enters here -- that is the whole anti-drift property (spec D4).
*/
#include <cmath>
#include <cstring>
#include <util2/C/base_type.h>
#include <vision/perception_types.hpp>   /* global TargetDetection / PerceptionSnapshot */
#include "frame/frame_convert.hpp"        /* Vec3 */
#include "perception/target_tracker.hpp" /* FrameTrackIds (stable ids per detection). */

struct CameraIntrinsics {
    f32 fx{0.0f}, fy{0.0f}, cx{0.0f}, cy{0.0f};
    u32 width{0}, height{0};
};

/* gz_x500_gimbal forward camera (PX4-Autopilot Tools/simulation/gz/models/gimbal/model.sdf):
   horizontal_fov=2.0 rad, 1280x720, Gazebo's camera plugin assumes square pixels (fx=fy).
   fx = width / (2*tan(hfov/2)) = 1280 / (2*tan(1.0)) ~= 410.88. cx/cy = image center.
   Matches the native resolution PerceptionRuntime consumes -- no resize in the camera
   pipeline before the FMU (spec 2026-08-05-visual-servoing-approach-design.md §9 R4).
   SINGLE definition -- fmu_node_base.hpp's kApproachCamera and detection_query_test.cpp
   both reference this constant rather than repeating the literal values. */
constexpr CameraIntrinsics kGzX500GimbalCam = { 410.88f, 410.88f, 640.0f, 360.0f, 1280, 720 };

struct TargetRelative {
    Vec3 dirFlu;          /* unit body-FLU direction to the target (forward+, left+, up+). */
    f32  range{0.0f};     /* metric distance, meters (from median_depth_cm/100).            */
    f32  errX{0.0f};      /* normalized horizontal bbox-center offset [-1..1] (right +).    */
    f32  errY{0.0f};      /* normalized vertical   bbox-center offset [-1..1] (down +).     */
    u64  age_us{0};       /* now - snapshot.host_stamp_us.                                  */
    bool found{false};
};

/* Finds the freshest detection whose label matches (dets[] is already the newest
   single-frame batch -- first match wins); back-projects its bbox center through the
   pinhole model, scales by metric range, converts camera->FLU. found=false if no match
   or the snapshot itself is not valid yet. */
static inline TargetRelative detectionByLabel(PerceptionSnapshot const& snap, char const* label,
                                               CameraIntrinsics const& cam, u64 now_us) {
    TargetRelative         out;
    TargetDetection const* best = nullptr;
    u32                    i;
    f32                    u, v, camX, camY, mag;
    Vec3                   raw;

    if (!snap.valid) return out;

    for (i = 0; i < snap.count; ++i) {
        if (std::strcmp(snap.dets[i].label, label) == 0) {
            best = &snap.dets[i];
            break;
        }
    }
    if (best == nullptr) return out;

    u    = 0.5f * static_cast<f32>(best->bbox_xmin + best->bbox_xmax);
    v    = 0.5f * static_cast<f32>(best->bbox_ymin + best->bbox_ymax);
    camX = (u - cam.cx) / cam.fx;
    camY = (v - cam.cy) / cam.fy;
    raw  = { 1.0f, -camX, -camY };
    mag  = std::sqrt(raw.x * raw.x + raw.y * raw.y + raw.z * raw.z);

    out.dirFlu = { raw.x / mag, raw.y / mag, raw.z / mag };
    out.range  = best->median_depth_cm / 100.0f;
    out.errX   = (u - cam.cx) / cam.cx;
    out.errY   = (v - cam.cy) / cam.cy;
    out.age_us = (now_us > snap.host_stamp_us) ? (now_us - snap.host_stamp_us) : 0;
    out.found  = true;
    return out;
}

/* FOLLOW instance tracker: detections carry no stable id, so among the label matches pick the
   bbox center nearest lastCenterPx (nearest-centroid across ticks), then back-project it like
   detectionByLabel. If the label match misses but exactly one thing is in frame, track that --
   YOLO flips class on unfamiliar meshes, same reason APPROACH falls back to presence. found=false
   when no valid snapshot or no candidate. Loop locals hoisted per the code-guidelines. */
static inline TargetRelative detectionNearestCenter(PerceptionSnapshot const& snap, char const* label,
                                                    f32 lastU, f32 lastV, CameraIntrinsics const& cam,
                                                    u64 now_us, f32 maxJumpPx = 0.0f) {
    TargetRelative         out;
    TargetDetection const* best = nullptr;
    f32                    bestD2 = 0.0f, u, v, du, dv, d2, camX, camY, mag;
    Vec3                   raw;
    u32                    i;

    if (!snap.valid) return out;
    for (i = 0; i < snap.count; ++i) {
        if (std::strcmp(snap.dets[i].label, label) != 0) continue;
        u  = 0.5f * static_cast<f32>(snap.dets[i].bbox_xmin + snap.dets[i].bbox_xmax);
        v  = 0.5f * static_cast<f32>(snap.dets[i].bbox_ymin + snap.dets[i].bbox_ymax);
        du = u - lastU; dv = v - lastV; d2 = du * du + dv * dv;
        if (best == nullptr || d2 < bestD2) { best = &snap.dets[i]; bestD2 = d2; }
    }
    if (best == nullptr && snap.count == 1) best = &snap.dets[0];  /* label flipped; only one in frame. */
    if (best == nullptr) return out;

    /* Jump gate: if the chosen same-label box is implausibly far from where the target was last,
       it is churn / a false positive, not our object -- reject it (found stays false) so the
       caller's coast/hover ladder holds instead of teleporting the lock. maxJumpPx<=0 disables. */
    if (maxJumpPx > 0.0f) {
        f32 bu = 0.5f * static_cast<f32>(best->bbox_xmin + best->bbox_xmax);
        f32 bv = 0.5f * static_cast<f32>(best->bbox_ymin + best->bbox_ymax);
        f32 jdu = bu - lastU, jdv = bv - lastV;
        if (jdu * jdu + jdv * jdv > maxJumpPx * maxJumpPx) return out;
    }

    u    = 0.5f * static_cast<f32>(best->bbox_xmin + best->bbox_xmax);
    v    = 0.5f * static_cast<f32>(best->bbox_ymin + best->bbox_ymax);
    camX = (u - cam.cx) / cam.fx;
    camY = (v - cam.cy) / cam.fy;
    raw  = { 1.0f, -camX, -camY };
    mag  = std::sqrt(raw.x * raw.x + raw.y * raw.y + raw.z * raw.z);
    out.dirFlu = { raw.x / mag, raw.y / mag, raw.z / mag };
    out.range  = best->median_depth_cm / 100.0f;
    out.errX   = (u - cam.cx) / cam.cx;
    out.errY   = (v - cam.cy) / cam.cy;
    out.age_us = (now_us > snap.host_stamp_us) ? (now_us - snap.host_stamp_us) : 0;
    out.found  = true;
    return out;
}


/* Back-project the detection carrying `track_id` this frame (FrameTrackIds is id-aligned to
   snap.dets[]). Same pinhole math as detectionByLabel. found=false if the id is not present.
   Lets a verb hold ONE specific tracked object regardless of label drift or list re-ordering --
   the disambiguation a label alone cannot give when two same-label people are in view. */
static inline TargetRelative detectionByTrackId(PerceptionSnapshot const& snap, FrameTrackIds const& ids,
                                                i32 track_id, CameraIntrinsics const& cam, u64 now_us) {
    TargetRelative out;
    f32            u, v, camX, camY, mag;
    Vec3           raw;
    u32            i, n;

    if (!snap.valid || track_id < 0) return out;
    n = (ids.count < snap.count) ? ids.count : snap.count;
    for (i = 0; i < n; ++i) {
        if (ids.id[i] != track_id) continue;
        TargetDetection const& best = snap.dets[i];
        u    = 0.5f * static_cast<f32>(best.bbox_xmin + best.bbox_xmax);
        v    = 0.5f * static_cast<f32>(best.bbox_ymin + best.bbox_ymax);
        camX = (u - cam.cx) / cam.fx;
        camY = (v - cam.cy) / cam.fy;
        raw  = { 1.0f, -camX, -camY };
        mag  = std::sqrt(raw.x * raw.x + raw.y * raw.y + raw.z * raw.z);
        out.dirFlu = { raw.x / mag, raw.y / mag, raw.z / mag };
        out.range  = best.median_depth_cm / 100.0f;
        out.errX   = (u - cam.cx) / cam.cx;
        out.errY   = (v - cam.cy) / cam.cy;
        out.age_us = (now_us > snap.host_stamp_us) ? (now_us - snap.host_stamp_us) : 0;
        out.found  = true;
        return out;
    }
    return out;
}


/* Nearest measurable obstacle range (m) across all detections, for the emergency boundary
   (spec 2026-08-07-spec-1 6.1). Pure/ROS-free so it is unit-testable next to detectionByLabel.
   Returns 0.0f when nothing is measurable (no valid snapshot, no detections, or every depth is
   missing from the two-rate lag) -- callers MUST read 0.0f as "unknown", never as an obstacle at
   zero range, or a depth-starved frame would trip the boundary. Loop locals hoisted per the
   code-guidelines. */
static inline f32 nearestDepthM(PerceptionSnapshot const& snap) {
    f32 nearest = 0.0f;
    f32 d;
    u32 i;

    if (!snap.valid) return 0.0f;
    for (i = 0; i < snap.count; ++i) {
        d = snap.dets[i].median_depth_cm / 100.0f;
        if (d <= 0.0f) continue;                       /* skip missing depth (two-rate lag). */
        if (nearest == 0.0f || d < nearest) nearest = d;
    }
    return nearest;
}


/* Depth-independent "looming" cue for the emergency boundary: the largest bounding-box fill
   fraction (bbox area / image area) across all detections. Close-range SITL depth over-reads
   badly or drops out (the APPROACH servo in fmu_node brakes on the same range and drove into a
   parked car in testing), so nearestDepthM alone cannot backstop a drone that has closed on a
   large object. A box that fills most of the frame means the object is right there, whatever the
   depth number says. Returns 0.0f when nothing measurable (no valid snapshot, no detections, or
   zero image area). Area-based: catches large objects (cars) well; a thin object (a standing
   person) never fills enough area to trip, so those still rely on depth. Loop locals hoisted per
   the code-guidelines. */
static inline f32 maxBboxFillFrac(PerceptionSnapshot const& snap, CameraIntrinsics const& cam) {
    f32 frame = static_cast<f32>(cam.width) * static_cast<f32>(cam.height);
    f32 best  = 0.0f;
    f32 w, h, frac;
    u32 i;

    if (!snap.valid || frame <= 0.0f) return 0.0f;
    for (i = 0; i < snap.count; ++i) {
        w = static_cast<f32>(snap.dets[i].bbox_xmax) - static_cast<f32>(snap.dets[i].bbox_xmin);
        h = static_cast<f32>(snap.dets[i].bbox_ymax) - static_cast<f32>(snap.dets[i].bbox_ymin);
        if (w <= 0.0f || h <= 0.0f) continue;
        frac = (w * h) / frame;
        if (frac > best) best = frac;
    }
    return best;
}
