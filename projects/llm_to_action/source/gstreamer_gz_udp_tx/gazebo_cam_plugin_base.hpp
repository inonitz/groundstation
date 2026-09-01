#pragma once
#include <util2/C/base_type.h>


constexpr u8          kOutCameraGStreamerFrameRate = 30u;
constexpr const char* kUdpHostIpAddress            = "127.0.0.1";

/* SITL camera UDP port -- owned here because this module IS the sim camera transport (the gz
   TX plugin sends frames on it; the RX's PX4/Gazebo branch receives on it). Distinct from the
   real Tello video port (kTelloVideoPort, tello_backend_base.hpp, protocol-fixed at 11111) so a
   SITL run and a Tello session can share a host without both binding 11111. */
constexpr u16         kSitlUdpCamPort              = 11112;