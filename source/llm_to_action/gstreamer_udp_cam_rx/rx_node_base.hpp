#pragma once
#include <sensor_msgs/msg/image.hpp>

using UDPCamMsgType   = sensor_msgs::msg::Image;
using hUDPCamMsgType  = UDPCamMsgType::SharedPtr;
using khUDPCamMsgType = UDPCamMsgType::ConstSharedPtr;
constexpr const char* kOutUDPCameraGstSinkName   = "completely_random_sink056";
constexpr const char* kOutUDPCameraRawFrameID    = "camera_link";
constexpr const char* kOutUDPCameraRawFrameTopic = "camera/stream";