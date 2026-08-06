/*
    Standalone, ROS-free unit test for detection_query.hpp.
    Build: g++ -std=c++17 -I <util2-include> -I <build_yolo-repo>/vision/include \
           detection_query_test.cpp -o /tmp/dqt && /tmp/dqt
*/
#include "perception/detection_query.hpp"
#include <cstdio>
#include <cstring>
#include <cassert>
#include <cmath>

static bool close(f32 a, f32 b) { return std::fabs(a - b) < 1e-4f; }

static PerceptionSnapshot makeSnapshot(char const* label, i32 xmin, i32 ymin, i32 xmax, i32 ymax,
                                        f32 depthCm) {
    PerceptionSnapshot snap;
    snap.valid = true;
    snap.count = 1;
    snap.host_stamp_us = 1000;
    std::snprintf(snap.dets[0].label, sizeof(FixedStringType), "%s", label);
    snap.dets[0].bbox_xmin = xmin;
    snap.dets[0].bbox_ymin = ymin;
    snap.dets[0].bbox_xmax = xmax;
    snap.dets[0].bbox_ymax = ymax;
    snap.dets[0].median_depth_cm = depthCm;
    return snap;
}

int main() {
    /* Real sim camera profile, defined once in detection_query.hpp -- not repeated here. */
    CameraIntrinsics cam = kGzX500GimbalCam;

    /* Bbox centered exactly on the principal point, known range -> dirFlu ~= {1,0,0}. */
    {
        PerceptionSnapshot snap = makeSnapshot("person", 600, 320, 680, 400, 250.0f);
        TargetRelative tr = detectionByLabel(snap, "person", cam, 2000);
        assert(tr.found);
        assert(close(tr.dirFlu.x, 1.0f));
        assert(close(tr.dirFlu.y, 0.0f));
        assert(close(tr.dirFlu.z, 0.0f));
        assert(close(tr.range, 2.5f));
        assert(close(tr.errX, 0.0f));
        assert(close(tr.errY, 0.0f));
        assert(tr.age_us == 1000);
    }

    /* Bbox offset right of center -> errX > 0, dirFlu.y < 0 (target to the right). */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 900, 320, 980, 400, 500.0f);
        TargetRelative tr = detectionByLabel(snap, "car", cam, 1000);
        assert(tr.found);
        assert(tr.errX > 0.0f);
        assert(tr.dirFlu.y < 0.0f);
    }

    /* Label mismatch -> found == false. */
    {
        PerceptionSnapshot snap = makeSnapshot("dog", 600, 320, 680, 400, 250.0f);
        TargetRelative tr = detectionByLabel(snap, "cat", cam, 1000);
        assert(!tr.found);
    }

    /* Invalid snapshot -> found == false regardless of contents. */
    {
        PerceptionSnapshot snap = makeSnapshot("person", 600, 320, 680, 400, 250.0f);
        snap.valid = false;
        TargetRelative tr = detectionByLabel(snap, "person", cam, 1000);
        assert(!tr.found);
    }

    std::printf("detection_query_test OK\n");
    return 0;
}
