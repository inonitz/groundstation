#include <chrono>
#include <future>
#include <iostream>
#include <thread>
#include <mavsdk.h>
// #include <mavsdk/mavsdk.h>
#include <plugins/action/action.h>
#include <plugins/telemetry/telemetry.h>


using namespace mavsdk;
using std::chrono::seconds;
using std::this_thread::sleep_for;


int main() {
    // 1. Initialize MAVSDK and connect to the Gazebo/PX4 SITL port
    Mavsdk mavsdk{Mavsdk::Configuration{ComponentType::GroundStation}};
    // 0.0.0.0 tells MAVSDK to listen on ALL network interfaces
    ConnectionResult connection_result = mavsdk.add_any_connection("udp://0.0.0.0:14540");
    if (connection_result != ConnectionResult::Success) {
        std::cerr << "Connection failed: " << connection_result << '\n';
        return 1;
    }

    // 2. Discover the system (the simulated drone)
    std::cout << "Waiting to discover system...\n";
    auto prom = std::promise<std::shared_ptr<System>>{};
    auto fut = prom.get_future();
    mavsdk.subscribe_on_new_system([&mavsdk, &prom]() {
        auto system = mavsdk.systems().back();
        if (system->has_autopilot()) {
            std::cout << "Discovered Autopilot\n";
            mavsdk.subscribe_on_new_system(nullptr); // Unsubscribe
            prom.set_value(system);
        }
    });

    if (fut.wait_for(seconds(10)) == std::future_status::timeout) {
        std::cerr << "No autopilot found, exiting.\n";
        return 1;
    }
    auto system = fut.get();

    // 3. Initialize Action and Telemetry plugins
    auto action = Action{system};
    auto telemetry = Telemetry{system};

    // 4. Wait for the drone to have a valid GPS lock (required for takeoff)
    std::cout << "Waiting for GPS lock...\n";
    while (!telemetry.health_all_ok()) {
        std::cout << "Waiting for system to be ready...\n";
        sleep_for(seconds(1));
    }
    std::cout << "System ready! GPS lock acquired.\n";

    // 5. Arm the drone
    std::cout << "Arming...\n";
    const Action::Result arm_result = action.arm();
    if (arm_result != Action::Result::Success) {
        std::cerr << "Arming failed: " << arm_result << '\n';
        return 1;
    }

    // 6. Takeoff
    std::cout << "Taking off...\n";
    const Action::Result takeoff_result = action.takeoff();
    if (takeoff_result != Action::Result::Success) {
        std::cerr << "Takeoff failed: " << takeoff_result << '\n';
        return 1;
    }

    // 7. Hover for 10 seconds
    std::cout << "Hovering for 10 seconds...\n";
    sleep_for(seconds(10));

    // 8. Land
    std::cout << "Landing...\n";
    const Action::Result land_result = action.land();
    if (land_result != Action::Result::Success) {
        std::cerr << "Landing failed: " << land_result << '\n';
        return 1;
    }

    std::cout << "Landing sequence initiated. Exiting app.\n";
    return 0;
}