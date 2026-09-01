/*
    Standalone, ROS-free unit test for perception/target_tracker.hpp.
    Build: g++ -std=c++17 -I <src/llm_to_action> -I <util2-include> -I <vision/include> \
           target_tracker_test.cpp -o /tmp/ttt && /tmp/ttt
    (the CMake target run_target_tracker_test wires the same include dirs.)
*/
#include "perception/target_tracker.hpp"
#include <cstdio>
#include <cstring>
#include <cassert>
#include <cmath>
#include <initializer_list>

struct Box { char const* label; i32 xmin, ymin, xmax, ymax; };

static PerceptionSnapshot makeSnap(std::initializer_list<Box> boxes, u64 stamp) {
    PerceptionSnapshot snap;
    snap.valid = true;
    snap.host_stamp_us = stamp;
    u32 i = 0;
    for (Box const& b : boxes) {
        std::snprintf(snap.dets[i].label, sizeof(FixedStringType), "%s", b.label);
        snap.dets[i].bbox_xmin = b.xmin; snap.dets[i].bbox_ymin = b.ymin;
        snap.dets[i].bbox_xmax = b.xmax; snap.dets[i].bbox_ymax = b.ymax;
        ++i;
    }
    snap.count = i;
    return snap;
}

int main() {
    TrackerParams p;   /* defaults: iouGate 0.3, distGatePx 80, maxAgeFrames 5 */

    /* 1. Persistence: a box drifting a few px per frame keeps its id. */
    {
        TargetTracker st;
        i32 firstId = -1;
        for (u32 f = 0; f < 6; ++f) {
            i32 x = 300 + static_cast<i32>(f) * 8;   /* drift 8px/frame -- well inside the gate */
            auto snap = makeSnap({ {"person", x, 300, x + 80, 460} }, 1000 + f * 100);
            auto ids = trackerUpdate(st, snap, 1000 + f * 100, p);
            assert(ids.count == 1);
            if (f == 0) firstId = ids.id[0];
            assert(ids.id[0] == firstId);   /* same tag every frame */
        }
        printf("  [1] persistence: id stable across drift OK (id=%d)\n", firstId);
    }

    /* 2. Coast through a one-frame blink: same id survives a single missed frame. */
    {
        TargetTracker st;
        auto s0 = makeSnap({ {"person", 300, 300, 380, 460} }, 1000);
        i32 id0 = trackerUpdate(st, s0, 1000, p).id[0];
        /* frame with NO detections (object blinked out). */
        PerceptionSnapshot empty; empty.valid = true; empty.count = 0; empty.host_stamp_us = 1100;
        auto e = trackerUpdate(st, empty, 1100, p);
        assert(e.count == 0);
        /* returns near where it was -> re-locks the same id (misses=1 < maxAge). */
        auto s1 = makeSnap({ {"person", 305, 302, 385, 462} }, 1200);
        i32 id1 = trackerUpdate(st, s1, 1200, p).id[0];
        assert(id1 == id0);
        printf("  [2] coast: id survives a one-frame blink OK (id=%d)\n", id1);
    }

    /* 3. Two people, distinct ids, no swap while separated across a crossing sweep. */
    {
        TargetTracker st;
        auto s0 = makeSnap({ {"person", 100, 300, 180, 460}, {"person", 900, 300, 980, 460} }, 1000);
        auto i0 = trackerUpdate(st, s0, 1000, p);
        i32 left = i0.id[0], right = i0.id[1];
        assert(left != right);
        /* they move toward each other but stay separated (gap ~200px >> drift); ids hold. */
        for (u32 f = 1; f <= 4; ++f) {
            i32 lx = 100 + static_cast<i32>(f) * 40;
            i32 rx = 900 - static_cast<i32>(f) * 40;
            auto s = makeSnap({ {"person", lx, 300, lx + 80, 460}, {"person", rx, 300, rx + 80, 460} }, 1000 + f * 100);
            auto ids = trackerUpdate(st, s, 1000 + f * 100, p);
            /* detection order is stable here, so slot0=left-mover, slot1=right-mover. */
            assert(ids.id[0] == left);
            assert(ids.id[1] == right);
        }
        printf("  [3] two targets: distinct ids, no swap while separated OK (%d,%d)\n", left, right);
    }

    /* 4. A genuinely new, far-away object gets a fresh id. */
    {
        TargetTracker st;
        auto s0 = makeSnap({ {"person", 100, 300, 180, 460} }, 1000);
        i32 a = trackerUpdate(st, s0, 1000, p).id[0];
        auto s1 = makeSnap({ {"person", 100, 300, 180, 460}, {"person", 1000, 300, 1080, 460} }, 1100);
        auto ids = trackerUpdate(st, s1, 1100, p);
        assert(ids.id[0] == a);          /* the old one keeps its id */
        assert(ids.id[1] != a);          /* the new far box is new    */
        printf("  [4] new object: fresh id OK (old=%d new=%d)\n", a, ids.id[1]);
    }

    /* 5. Gone past the coast window -> retired -> returns as a NEW id (the honest limit). */
    {
        TargetTracker st;
        auto s0 = makeSnap({ {"person", 300, 300, 380, 460} }, 1000);
        i32 id0 = trackerUpdate(st, s0, 1000, p).id[0];
        PerceptionSnapshot empty; empty.valid = true; empty.count = 0;
        for (u32 f = 0; f < p.maxAgeFrames + 1; ++f) {       /* miss more than maxAge frames */
            empty.host_stamp_us = 1100 + f * 100;
            trackerUpdate(st, empty, 1100 + f * 100, p);
        }
        auto s1 = makeSnap({ {"person", 300, 300, 380, 460} }, 3000);
        i32 id1 = trackerUpdate(st, s1, 3000, p).id[0];
        assert(id1 != id0);
        printf("  [5] age-out: return past coast window -> new id OK (old=%d new=%d)\n", id0, id1);
    }

    /* 6. Metadata: confirm rides along; findById / unique-attribute recovery + ambiguity guard. */
    {
        TargetTracker st;
        auto s0 = makeSnap({ {"person", 100, 300, 180, 460}, {"person", 900, 300, 980, 460} }, 1000);
        auto ids = trackerUpdate(st, s0, 1000, p);
        i32 target = ids.id[0];
        assert(trackerSetConfirmed(st, target, "has_hat"));
        /* persists across a frame + is found by id */
        auto s1 = makeSnap({ {"person", 108, 300, 188, 460}, {"person", 900, 300, 980, 460} }, 1100);
        trackerUpdate(st, s1, 1100, p);
        Track const* t = trackerFindById(st, target);
        assert(t && t->confirmed_target && std::strcmp(t->attribute, "has_hat") == 0);
        /* unique-attribute recovery finds exactly it */
        Track const* byAttr = trackerFindByAttribute(st, "has_hat");
        assert(byAttr && byAttr->id == target);
        /* ambiguity guard: a second has_hat -> refuse (nullptr) */
        assert(trackerSetConfirmed(st, ids.id[1], "has_hat"));
        assert(trackerFindByAttribute(st, "has_hat") == nullptr);
        printf("  [6] metadata: persists, id/attribute lookup + ambiguity guard OK\n");
    }

    /* 7. cosineSim sanity (reserved embedding path). */
    {
        f32 a[4] = { 1, 0, 0, 0 }, b[4] = { 1, 0, 0, 0 }, c[4] = { 0, 1, 0, 0 };
        assert(std::fabs(cosineSim(a, b, 4) - 1.0f) < 1e-4f);
        assert(std::fabs(cosineSim(a, c, 4) - 0.0f) < 1e-4f);
        printf("  [7] cosineSim: identical=1, orthogonal=0 OK\n");
    }

    printf("target_tracker_test: ALL OK\n");
    return 0;
}
