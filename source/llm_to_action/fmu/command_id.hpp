#pragma once
/*
    CommandID -- the FMU's platform-neutral command tags -- and the ONE place that maps a
    VLM/canned action STRING to that tag.

    Split out of fmu_node.hpp so the string->id mapping is a PURE, ROS-free free function a unit
    test can call without spinning up the node (see test/fmu_translate_test.cpp). fmu_node.hpp
    includes this and switches on the returned id in translateToBaseCommands(); no other file owns
    a second copy of the action vocabulary.
*/
#include <string_view>
#include <util2/C/base_type.h>


enum class CommandID : u8 {
    TAKEOFF  = 0,
    LAND     = 1,
    STOP     = 2,
    GO       = 3,
    CURVE    = 4,
    ROTATE   = 5,
    ORBIT    = 6,
    SEARCH   = 7,
    REASSESS = 8,
    APPROACH = 9,
    FOLLOW   = 10,
    HOVER    = 11,
    MAX_ID   = 12   /* count, and the "unknown action" sentinel commandIdFromAction returns. */
};

/* Map a VLM/canned plan action string to its CommandID. Total and pure: returns MAX_ID for any
   string the translate path does not handle (CURVE/REASSESS are internal commands, never emitted
   as a plan "action"). String comparison lives here, isolated and unit-tested; the caller then
   switches on the id. */
inline CommandID commandIdFromAction(std::string_view action) {
    if (action == "takeoff")  return CommandID::TAKEOFF;
    if (action == "land")     return CommandID::LAND;
    if (action == "stop")     return CommandID::STOP;
    if (action == "hover")    return CommandID::HOVER;
    if (action == "go")       return CommandID::GO;
    if (action == "rotate")   return CommandID::ROTATE;
    if (action == "approach") return CommandID::APPROACH;
    if (action == "follow")   return CommandID::FOLLOW;
    if (action == "orbit")    return CommandID::ORBIT;
    if (action == "search")   return CommandID::SEARCH;
    return CommandID::MAX_ID;
}

/* Inverse of commandIdFromAction: a CommandID -> its short verb string, for logs and the
   dashboard's executed-command list. Total; MAX_ID / anything unmapped -> "?". Kept next to its
   inverse so the action vocabulary has exactly one home. */
inline const char* cmdName(CommandID id) {
    switch (id) {
        case CommandID::TAKEOFF:  return "takeoff";
        case CommandID::LAND:     return "land";
        case CommandID::STOP:     return "stop";
        case CommandID::HOVER:    return "hover";
        case CommandID::GO:       return "go";
        case CommandID::CURVE:    return "curve";
        case CommandID::ROTATE:   return "rotate";
        case CommandID::ORBIT:    return "orbit";
        case CommandID::SEARCH:   return "search";
        case CommandID::REASSESS: return "reassess";
        case CommandID::APPROACH: return "approach";
        case CommandID::FOLLOW:   return "follow";
        default:                  return "?";
    }
}
