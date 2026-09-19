# For the llm_to_action owner: clear the slam dependency

Context: we are restructuring the groundstation repo. projects/slam is being retired -- archived,
then deleted. It was the Tello-stabilization experiment: monocular SLAM at 20 Hz could not hold
when the Tello's VPS dropped, and the Tello is no longer our target platform. So slam goes away.

The blocker: llm_to_action depends on projects/slam. Specifically,
projects/llm_to_action/source/tello_backend/test/tello_slam_hold.cpp includes headers that exist
only in projects/slam/source/ (slam_pose_bridge.hpp, slam_recovery_fsm.hpp, slam2.hpp,
hover_hold_control.hpp), and its CMake target in
projects/llm_to_action/source/tello_backend/CMakeLists.txt (around lines 82-95) adds projects/slam
to the include path. Archiving projects/slam would break that build target.

The ask: remove the slam-hold parts from llm_to_action so projects/slam can be archived without
breaking your build. Keep only the core tello backend. You know this tree far better than I do --
decide exactly what to remove (the tello_slam_hold test target, its CMake entry, and any other
slam-dependent pieces) and how.

Coordination: projects/slam will NOT be archived until you confirm this is done. Reply when the
slam dependency is cleared.
