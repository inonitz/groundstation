#pragma once
#include <bits/chrono.h>
#include <util2/C/macro.h>
#include <util2/C/base_type.h>
#include <rclcpp/rclcpp.hpp>


using TimerSharedPtr = typename rclcpp::TimerBase::SharedPtr;
template<typename T> using PublisherPtr  = typename rclcpp::Publisher<T>::SharedPtr;
template<typename T> using SubscriberPtr = typename rclcpp::Subscription<T>::SharedPtr;

// template<typename T> using ServiceClientPtr = typename rclcpp::Service<T>::SharedPtr;
