#pragma once
#include "async_key.hpp"
#include "key_codes.hpp"
#include "keyboard_node_base.hpp"
#include <rclcpp/rclcpp.hpp>


// https://docs.ros2.org/latest/api/rclcpp/classrclcpp_1_1Node.html
class KeyboardTeleop : public rclcpp::Node {
public:
    KeyboardTeleop() : Node("keyboard_teleop") {        
        /* Construct the raw-key publisher BEFORE binding keys (the callback publishes to it). */
        m_rawKeyEvent = this->create_publisher<KeyboardRawInputType>(kOutKeyboardRawTopic, 10);
        bool hook_success = m_keyHook.create();
        if (!hook_success) {
            RCLCPP_ERROR(this->get_logger(), "FATAL: AsyncKeyHook failed to create threads/hooks!");
        } else {
            RCLCPP_INFO(this->get_logger(), "AsyncKeyHook successfully attached.");
        }
        auto cb = [this](KeyCodeEnum k, KeyAction a){ this->keyCallback(k, a); };
        

        

        m_keyHook.bindKey(KeyCodeEnum::W, cb);
        m_keyHook.bindKey(KeyCodeEnum::S, cb);
        m_keyHook.bindKey(KeyCodeEnum::A, cb);
        m_keyHook.bindKey(KeyCodeEnum::D, cb);
        m_keyHook.bindKey(KeyCodeEnum::H, cb);
        m_keyHook.bindKey(KeyCodeEnum::UpArrow, cb);
        m_keyHook.bindKey(KeyCodeEnum::DownArrow, cb);
        m_keyHook.bindKey(KeyCodeEnum::LeftArrow, cb);
        m_keyHook.bindKey(KeyCodeEnum::RightArrow, cb);
        m_keyHook.bindKey(KeyCodeEnum::Enter, cb);
        m_keyHook.bindKey(KeyCodeEnum::Space, cb);
        return;
    }
    
    ~KeyboardTeleop() { 
        m_keyHook.destroy();
    }

private:
    void keyCallback(KeyCodeEnum k, KeyAction action) {
        RCLCPP_INFO(this->get_logger(), "Raw Key Event -> Code: %d, Action: %d", 
            static_cast<int>(k), 
            static_cast<int>(action)
        );

        // 1. Publish raw array
        KeyboardRawInputType _;
        _.data.push_back(static_cast<int32_t>(k));
        _.data.push_back(static_cast<int32_t>(action));
        m_rawKeyEvent->publish(_);
        return;
    }

    PublisherPtr<KeyboardRawInputType> m_rawKeyEvent;
    rclcpp::TimerBase::SharedPtr       m_timer;
    AsyncKeyHook                       m_keyHook;
    std::mutex                         m_lock;
};
