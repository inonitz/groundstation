#include <rclcpp/publisher.hpp>
#include <rclcpp/rclcpp.hpp>
#include <px4_msgs/msg/vehicle_status.hpp>
#include "async_key.hpp"


using namespace rclcpp;


class Px4Listener : public rclcpp::Node {
private:
    Subscription<px4_msgs::msg::VehicleStatus>::SharedPtr m_subscription;

public:
    Px4Listener() : Node("px4_groundstation_listener") {
        
        // 1. PX4 DDS Bridge REQUIRES the Sensor Data QoS profile (Best Effort)
        // rmw_qos_profile_t qos_profile = rmw_qos_profile_sensor_data;
        // auto qos = rclcpp::QoS(rclcpp::QoSInitialization(qos_profile.history, 1), qos_profile);
        QoS qos = SensorDataQoS();

        // 2. Subscribe to the vehicle status topic
        m_subscription = this->create_subscription<px4_msgs::msg::VehicleStatus>(
            "/fmu/out/vehicle_status_v4", 
            qos,
            [this](const px4_msgs::msg::VehicleStatus::SharedPtr msg) {
                RCLCPP_INFO(this->get_logger(), 
                    "Telemetry Rx -> Arming State: %d | Nav State: %d", 
                    msg->arming_state, 
                    msg->nav_state
                );
            }
        );
    }
};


// class RosKeyboardNode : public rclcpp::Publisher<TypeAdapter<KeyCode>> {
// public:
//     RosKeyboardNode() : Node("ros2_async_keyboard_publisher") {
//         m_keyThread.create();
//         m_keyThread.bindKey(KeyCode::Any, AsyncKeyHook::Callback{keyProcessor});
//     }

//     ~RosKeyboardNode() {
//         m_keyThread.destroy();
//     }

// private:
//     static void keyProcessor(KeyCode key) {

//     }

// private:
//     AsyncKeyHook m_keyThread;
// };


int main(int argc, char * argv[]) {
    setvbuf(stdout, NULL, _IONBF, 0);


    rclcpp::init(argc, argv);
    // rclcpp::spin(std::make_shared<RosKeyboardNode>());
    
    rclcpp::spin(std::make_shared<Px4Listener>());
    rclcpp::shutdown();
    return 0;
}