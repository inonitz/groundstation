#pragma once
#include <std_msgs/msg/string.hpp>


constexpr const char* kOutASRServerTranscriptionTopic = "/asr_server/transcribe";
using ASRTextType = std_msgs::msg::String;