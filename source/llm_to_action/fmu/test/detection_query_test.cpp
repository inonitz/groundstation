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

    /* nearestDepthM: single detection -> its depth in metres. */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 600, 320, 680, 400, 250.0f);
        assert(close(nearestDepthM(snap), 2.5f));
    }

    /* nearestDepthM: returns the MINIMUM depth across detections (the nearest obstacle). */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 600, 320, 680, 400, 500.0f);
        snap.count = 3;
        std::snprintf(snap.dets[1].label, sizeof(FixedStringType), "%s", "person");
        snap.dets[1].median_depth_cm = 120.0f;   /* nearest */
        std::snprintf(snap.dets[2].label, sizeof(FixedStringType), "%s", "dog");
        snap.dets[2].median_depth_cm = 300.0f;
        assert(close(nearestDepthM(snap), 1.2f));
    }

    /* nearestDepthM: a detection with missing depth (<=0) is skipped, not read as zero range. */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 600, 320, 680, 400, 0.0f);   /* missing */
        snap.count = 2;
        std::snprintf(snap.dets[1].label, sizeof(FixedStringType), "%s", "person");
        snap.dets[1].median_depth_cm = 400.0f;   /* the only measurable one */
        assert(close(nearestDepthM(snap), 4.0f));
    }

    /* nearestDepthM: nothing measurable -> 0.0f ("unknown"), never a false obstacle at zero range. */
    {
        PerceptionSnapshot missing = makeSnapshot("car", 600, 320, 680, 400, 0.0f);
        assert(close(nearestDepthM(missing), 0.0f));         /* only det has no depth */

        PerceptionSnapshot empty = makeSnapshot("car", 600, 320, 680, 400, 250.0f);
        empty.count = 0;
        assert(close(nearestDepthM(empty), 0.0f));           /* no detections */

        PerceptionSnapshot invalid = makeSnapshot("car", 600, 320, 680, 400, 250.0f);
        invalid.valid = false;
        assert(close(nearestDepthM(invalid), 0.0f));         /* invalid snapshot */
    }

    /* maxBboxFillFrac: fill = bbox area / frame area (1280x720). 640x720 -> 0.5. */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 320, 0, 960, 720, 150.0f);
        assert(close(maxBboxFillFrac(snap, cam), 0.5f));
    }

    /* maxBboxFillFrac: a small far box fills little of the frame. */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 600, 320, 680, 400, 800.0f);   /* 80x80 */
        assert(maxBboxFillFrac(snap, cam) < 0.01f);
    }

    /* maxBboxFillFrac: returns the LARGEST fill across detections (the closest looming object). */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 600, 320, 680, 400, 500.0f);   /* small */
        snap.count = 2;
        std::snprintf(snap.dets[1].label, sizeof(FixedStringType), "%s", "car");
        snap.dets[1].bbox_xmin = 320; snap.dets[1].bbox_ymin = 0;
        snap.dets[1].bbox_xmax = 960; snap.dets[1].bbox_ymax = 720;   /* 0.5 -- the looming one */
        snap.dets[1].median_depth_cm = 90.0f;
        assert(close(maxBboxFillFrac(snap, cam), 0.5f));
    }

    /* maxBboxFillFrac: degenerate box (xmax<=xmin) is skipped, not counted as negative area. */
    {
        PerceptionSnapshot snap = makeSnapshot("car", 900, 400, 800, 300, 100.0f);   /* inverted */
        assert(close(maxBboxFillFrac(snap, cam), 0.0f));
    }

    /* maxBboxFillFrac: invalid and empty snapshots -> 0.0f. */
    {
        PerceptionSnapshot invalid = makeSnapshot("car", 320, 0, 960, 720, 150.0f);
        invalid.valid = false;
        assert(close(maxBboxFillFrac(invalid, cam), 0.0f));

        PerceptionSnapshot empty = makeSnapshot("car", 320, 0, 960, 720, 150.0f);
        empty.count = 0;
        assert(close(maxBboxFillFrac(empty, cam), 0.0f));
    }

    std::printf("detection_query_test OK\n");
    return 0;
}
