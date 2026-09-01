#pragma once
#include <util/base.hpp>
#include <std_msgs/msg/int32_multi_array.hpp>


constexpr const char* kOutKeyboardRawTopic = "/keyboard/in/raw";
using KeyboardRawInputType = std_msgs::msg::Int32MultiArray;
