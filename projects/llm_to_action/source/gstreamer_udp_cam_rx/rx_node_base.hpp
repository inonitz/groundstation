#pragma once
#include <sensor_msgs/msg/image.hpp>

/* 
    k = constant 
    h = handle i.e. pointer to a resource
    CameraPipeline - the receiver's decoded-frame output. The SOURCE varies by
    backend (UDP for PX4/Tello, TCP for DJI); the published frames are uniform.
    Figure out the rest on your own    
*/
using CameraPipelineMsgType   = sensor_msgs::msg::Image;
using hCameraPipelineMsgType  = CameraPipelineMsgType::SharedPtr;
using khCameraPipelineMsgType = CameraPipelineMsgType::ConstSharedPtr;
constexpr const char* kOutCameraPipelineGstSinkName   = "completely_random_sink056";
constexpr const char* kOutCameraPipelineRawFrameID    = "camera_link";
constexpr const char* kOutCameraPipelineRawFrameTopic = "camera/stream";
