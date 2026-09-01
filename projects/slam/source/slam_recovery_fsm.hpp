#pragma once
/*
    slam_recovery_fsm -- the bounded "degrade, then land" recovery logic for a Tello
    SLAM loss, as a pure state machine.

    NO ROS, NO backend -- depends only on f32, so it is unit-testable with a
    standalone g++ (see test/slam_recovery_fsm_test.cpp) and wired by the C2/C3 node
    without change. The node feeds it, per tick: is tracking VERIFIED-alive (from the
    tracking-state topic + PnP inlier count), are we mid-SEARCH, and dt. It returns
    the recovery action to command; the node turns that into set_velocity / a rotate
    / a land.

    Why a hard land is the floor, not a nicety: on a low-texture patch the VPS and
    SLAM co-fail together, `vgx/vgy` read a false zero, and there is NO sensor left to
    arrest XY drift. So blind flight is never prolonged -- we hold briefly for a
    re-track, optionally degrade to a position-free in-place rotate-scan while
    SEARCHing (rotation needs no position), and otherwise land.

    The FSM owns SLAM recovery only. If the VLM finds the target during a rotate-scan,
    that is a task-level switch to the position-free FOLLOW, handled by the caller;
    here a successful re-track simply returns to NOMINAL.
*/
#include <util2/C/base_type.h>


enum class RecoveryState : u8 { TRACKING, LOST_HOLD, SEARCH_ROTATE, LANDING };

/* What the node should command this tick. NOMINAL = no recovery override, let the
   active task run. */
enum class RecoveryAction : u8 { NOMINAL, ZERO_VELOCITY, ROTATE_SCAN, LAND };

struct RecoveryConfig {
    f32 mk_relocHoldS{2.0f};   /* hold + attempt re-track this long before giving up. */
    f32 mk_scanBudgetS{8.0f};  /* rotate-scan this long before landing.               */
};

struct RecoveryFsm {
    RecoveryState  m_state{RecoveryState::TRACKING};
    f32            m_timerS{0.0f};
    RecoveryConfig m_cfg{};

    void reset() {
        m_state  = RecoveryState::TRACKING;
        m_timerS = 0.0f;
        return;
    }

    /* One control tick. trackingAlive is the VERIFIED re-track signal (alive AND
       enough PnP inliers), never a bare appearance match. */
    RecoveryAction tick(bool trackingAlive, bool inSearch, f32 dt) {
        switch (m_state) {
        case RecoveryState::TRACKING:
            if (!trackingAlive) {
                m_state  = RecoveryState::LOST_HOLD;
                m_timerS = 0.0f;
                return RecoveryAction::ZERO_VELOCITY;   /* stop translating at once. */
            }
            return RecoveryAction::NOMINAL;

        case RecoveryState::LOST_HOLD:
            if (trackingAlive) {
                m_state  = RecoveryState::TRACKING;
                return RecoveryAction::NOMINAL;         /* re-tracked inside the window. */
            }
            m_timerS += dt;
            if (m_timerS >= m_cfg.mk_relocHoldS) {
                if (inSearch) {
                    m_state  = RecoveryState::SEARCH_ROTATE;
                    m_timerS = 0.0f;
                    return RecoveryAction::ROTATE_SCAN;
                }
                m_state = RecoveryState::LANDING;
                return RecoveryAction::LAND;
            }
            return RecoveryAction::ZERO_VELOCITY;       /* keep holding, keep feeding frames. */

        case RecoveryState::SEARCH_ROTATE:
            if (trackingAlive) {
                m_state  = RecoveryState::TRACKING;
                return RecoveryAction::NOMINAL;
            }
            m_timerS += dt;
            if (m_timerS >= m_cfg.mk_scanBudgetS) {
                m_state = RecoveryState::LANDING;
                return RecoveryAction::LAND;
            }
            return RecoveryAction::ROTATE_SCAN;

        case RecoveryState::LANDING:
        default:
            return RecoveryAction::LAND;                /* terminal -- committed to landing. */
        }
    }
};
