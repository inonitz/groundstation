#pragma once
#include <mutex>
#include "base.hpp"
#include "async_key.hpp"
#include "key_codes.hpp"


// constexpr const char* kPx4KeyboardCmdVelTopic = "/px4_keyboard/arm_msg";
// constexpr const char* kPx4KeyboardTwistTopic  = "/px4_keyboard/cmd_vel";
// using Px4KeyboardTwistType = geometry_msgs::msg::Twist;
// using Px4KeyboardArmType   = std_msgs::msg::Bool;


// https://docs.ros2.org/latest/api/rclcpp/classrclcpp_1_1Node.html
class KeyboardTeleop : public rclcpp::Node {
public:
    KeyboardTeleop() : Node("px4_keyboard_teleop") {
        // Publish to standard velocity topic at 20Hz
        // https://docs.ros2.org/latest/api/rclcpp/classrclcpp_1_1Publisher.html
        // https://docs.ros2.org/latest/api/rclcpp/classrclcpp_1_1TimerBase.html
        m_twist  = this->create_publisher<KeyboardTwistType>(kOutKeyboardTwistTopic, 10);
        m_arming = this->create_publisher<KeyboardArmType>(kOutKeyboardArmStateTopic, 10);
        m_rawKeyEvent    = this->create_publisher<KeyboardRawInputType>(kOutKeyboardRawTopic, 10);
        m_timer = this->create_wall_timer(
            std::chrono::milliseconds(50), 
            std::bind(&KeyboardTeleop::timerCallback, this)
        );
        
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

        // 2. Handle Inputs for Px4 Drone
        if (action == KeyAction::UNKNOWN) {
            return;
        }
    
        // Handle Arming Toggle on Enter key press
        std::lock_guard<std::mutex> lock(m_lock);
        if (k == KeyCodeEnum::Enter && action == KeyAction::PRESSED) {
            m_armState = !m_armState;
            
            KeyboardArmType _{};
            _.data = m_armState;

            m_arming->publish(_);
            return;
        }

        // REPEATED acts same as PRESSED. RELEASED zeros the axis.
        double pos_val = (action == KeyAction::RELEASED) ? 0.0 : 1.0;
        double neg_val = (action == KeyAction::RELEASED) ? 0.0 : -1.0;
        
        // REP-103 mapping
        if (k == KeyCodeEnum::W) m_velcmd.linear.x = pos_val;
        else if (k == KeyCodeEnum::S) m_velcmd.linear.x = neg_val;
        else if (k == KeyCodeEnum::A) m_velcmd.linear.y = pos_val;  // Left is +Y
        else if (k == KeyCodeEnum::D) m_velcmd.linear.y = neg_val; // Right is -Y
        else if (k == KeyCodeEnum::UpArrow) m_velcmd.linear.z = pos_val;
        else if (k == KeyCodeEnum::DownArrow) m_velcmd.linear.z = neg_val;
        else if (k == KeyCodeEnum::LeftArrow) m_velcmd.angular.z = pos_val; // CCW is +Yaw
        else if (k == KeyCodeEnum::RightArrow) m_velcmd.angular.z = neg_val; // CW is -Yaw
        return;
    }


    void timerCallback() {
        KeyboardTwistType msg;
        {
            std::lock_guard<std::mutex> lock(m_lock);
            msg = m_velcmd;
        }

        RCLCPP_DEBUG(this->get_logger(), "Keyboard Timer Tick -> Pub Twist (Linear X: %.1f, Z: %.1f)", 
            msg.linear.x, 
            msg.linear.z
        );
        m_twist->publish(msg);
    }

    PublisherPtr<KeyboardTwistType>    m_twist;
    PublisherPtr<KeyboardArmType>      m_arming;
    PublisherPtr<KeyboardRawInputType> m_rawKeyEvent;
    rclcpp::TimerBase::SharedPtr          m_timer;
    AsyncKeyHook                          m_keyHook;
    KeyboardTwistType                  m_velcmd;
    bool                                  m_armState;
    std::mutex                            m_lock;
};
