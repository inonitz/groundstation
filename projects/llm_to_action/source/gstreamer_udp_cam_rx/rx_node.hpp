#include "rx_node_base.hpp"
#include "generic_backend/generic_backend_types.hpp"  /* BackendType */
#include "util/base.hpp"
#include <gst/gst.h>
#include <string>


class GstReceiverNode : public rclcpp::Node {
public:
    explicit GstReceiverNode(BackendType backend, std::string djiHost = "127.0.0.1");
    ~GstReceiverNode() override;

private:
    void PollSampleCb();
    void PollBusCb();

private:
    PublisherPtr<CameraPipelineMsgType> m_pubCamFrames;
    TimerSharedPtr              m_pull_timer;
    TimerSharedPtr              m_bus_timer;
    GstElement* m_pipeline = nullptr;
    GstElement* m_sink     = nullptr;
    GstBus*     m_bus      = nullptr;
};