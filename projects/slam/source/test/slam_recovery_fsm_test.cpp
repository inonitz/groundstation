/*
    Standalone, hardware-free unit test for slam/slam_recovery_fsm.hpp.
    Covers every transition of the degrade-then-land recovery:
      - nominal tracking -> no override
      - loss -> immediate ZERO_VELOCITY, short hold, re-track resumes
      - hold timeout while NOT searching -> LAND
      - hold timeout while searching -> ROTATE_SCAN, then re-track resumes
      - rotate-scan budget exhausted -> LAND (terminal)
    Build:
      g++ -std=c++17 -I source/slam -I <util2-include> \
          source/slam/test/slam_recovery_fsm_test.cpp -o /tmp/srft && /tmp/srft
*/
#include "slam_recovery_fsm.hpp"
#include <cstdio>
#include <cassert>

int main() {
    const f32 dt = 0.1f;

    /* --- nominal tracking: no recovery override. --- */
    {
        RecoveryFsm fsm;
        for (int i = 0; i < 10; ++i)
            assert(fsm.tick(/*alive*/ true, /*inSearch*/ false, dt) == RecoveryAction::NOMINAL);
        assert(fsm.m_state == RecoveryState::TRACKING);
    }

    /* --- loss -> ZERO_VELOCITY immediately, then a re-track inside the window resumes. --- */
    {
        RecoveryFsm fsm;
        assert(fsm.tick(false, false, dt) == RecoveryAction::ZERO_VELOCITY);
        assert(fsm.m_state == RecoveryState::LOST_HOLD);
        /* half a second of holding, still blind */
        for (int i = 0; i < 5; ++i)
            assert(fsm.tick(false, false, dt) == RecoveryAction::ZERO_VELOCITY);
        /* re-track before the hold expires -> back to nominal */
        assert(fsm.tick(true, false, dt) == RecoveryAction::NOMINAL);
        assert(fsm.m_state == RecoveryState::TRACKING);
    }

    /* --- hold times out while NOT searching -> LAND. --- */
    {
        RecoveryFsm fsm;                       /* relocHoldS = 2.0 s, dt = 0.1 -> 20 ticks */
        fsm.tick(false, false, dt);            /* enter LOST_HOLD */
        RecoveryAction a = RecoveryAction::ZERO_VELOCITY;
        for (int i = 0; i < 30; ++i) a = fsm.tick(false, /*inSearch*/ false, dt);
        assert(a == RecoveryAction::LAND);
        assert(fsm.m_state == RecoveryState::LANDING);
        /* terminal: stays landing */
        assert(fsm.tick(true, false, dt) == RecoveryAction::LAND);
    }

    /* --- hold times out while SEARCHing -> ROTATE_SCAN, then a re-track resumes. --- */
    {
        RecoveryFsm fsm;
        fsm.tick(false, true, dt);             /* enter LOST_HOLD (inSearch) */
        RecoveryAction a = RecoveryAction::ZERO_VELOCITY;
        for (int i = 0; i < 25; ++i) a = fsm.tick(false, /*inSearch*/ true, dt);
        assert(a == RecoveryAction::ROTATE_SCAN);
        assert(fsm.m_state == RecoveryState::SEARCH_ROTATE);
        /* found the scene again mid-scan -> nominal */
        assert(fsm.tick(true, true, dt) == RecoveryAction::NOMINAL);
        assert(fsm.m_state == RecoveryState::TRACKING);
    }

    /* --- rotate-scan budget exhausted with no re-track -> LAND. --- */
    {
        RecoveryFsm fsm;
        fsm.tick(false, true, dt);             /* LOST_HOLD */
        for (int i = 0; i < 25; ++i) fsm.tick(false, true, dt);   /* -> SEARCH_ROTATE */
        assert(fsm.m_state == RecoveryState::SEARCH_ROTATE);
        RecoveryAction a = RecoveryAction::ROTATE_SCAN;
        for (int i = 0; i < 90; ++i) a = fsm.tick(false, true, dt);  /* scanBudget 8s = 80 ticks */
        assert(a == RecoveryAction::LAND);
        assert(fsm.m_state == RecoveryState::LANDING);
    }

    std::printf("slam_recovery_fsm_test: ALL PASS\n");
    return 0;
}
