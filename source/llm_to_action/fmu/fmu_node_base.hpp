#pragma once
#include <util2/C/base_type.h>


constexpr u32 kMillisecondsInOneSecond  = 1000;
constexpr u32 kVlmReassessmentRateMs    = kMillisecondsInOneSecond * 5;
constexpr u32 kYoLoSegmentRefreshRateHz = 25;
constexpr u32 kYoLoSegmentRefreshRateMs = kMillisecondsInOneSecond / 25;
constexpr u32 kYoLoDepthRefreshRateHz   = 30;
constexpr u32 kYoLoDepthRefreshRateMs   = kMillisecondsInOneSecond / 30;
constexpr u32 kCmdQueueUpdateRateHz     = 20;
constexpr u32 kCmdQueueUpdateRateMs     = kMillisecondsInOneSecond / 20;
constexpr u32 kDefaultPromptHistorySize = 256;