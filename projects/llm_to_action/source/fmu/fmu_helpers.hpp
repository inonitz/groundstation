#pragma once
/*
    Pure, node-independent FMU helpers -- lifted out of fmu_node.hpp so they are unit-testable
    without spinning up a ROS node (see test/fmu_translate_test.cpp). Nothing here touches member
    state, the backend, perception, or ROS. The AUDIT finding: most of the node's "small helpers"
    are NOT pure -- approachMotionNominal reads a member, bboxRangeDir/bboxToEnuAnchor use
    m_perception + ROS logging, updateCannedApproachRig is heavy member state -- so they correctly
    stay methods on FlightManagementUnitNode. Only these two are genuinely pure.
*/
#include <cctype>
#include <cstring>
#include "frame/frame_convert.hpp"   /* Vec3, f32 */


/* Perpendicular component of measVel relative to forwardUnit (assumed unit length); damps the
   pursuit-arc residual left after switching to a measured bearing (spec §9 R1). */
inline Vec3 lateralComponent(Vec3 measVel, Vec3 forwardUnit) {
    f32 along = measVel.x * forwardUnit.x + measVel.y * forwardUnit.y + measVel.z * forwardUnit.z;
    return { measVel.x - along * forwardUnit.x,
             measVel.y - along * forwardUnit.y,
             measVel.z - along * forwardUnit.z };
}

/* The VLM names targets in natural language ("human in red", "red person"), but YOLO emits COCO
   class labels ("person"). An exact strcmp then never matches, so SEARCH can stare straight at the
   target and never register it -- it just keeps advancing (into the rocks). Match a person
   detection whenever the requested target refers to a human; WHICH person is red stays the VLM's
   job via the image + bbox. */
inline bool labelMatchesTarget(const char* detLabel, const char* target) {
    if (!detLabel || !target) return false;
    if (std::strcmp(detLabel, target) == 0) return true;
    char t[128]; size_t i = 0;
    for (; target[i] && i < sizeof(t) - 1; ++i)
        t[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(target[i])));
    t[i] = '\0';
    const bool targetIsPerson =
        std::strstr(t, "human") || std::strstr(t, "person") || std::strstr(t, "people") ||
        std::strstr(t, "man")   || std::strstr(t, "woman")  || std::strstr(t, "guy")    ||
        std::strstr(t, "someone")|| std::strstr(t, "boy")   || std::strstr(t, "girl");
    return targetIsPerson && std::strcmp(detLabel, "person") == 0;
}
