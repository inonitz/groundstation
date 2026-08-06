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
