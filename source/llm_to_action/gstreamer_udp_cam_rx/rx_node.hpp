#include "rx_node_base.hpp"
#include "util/base.hpp"
#include <gst/gst.h>


class GstReceiverNode : public rclcpp::Node {
public:
    explicit GstReceiverNode(bool bUseTelloPipeline = false);
    ~GstReceiverNode() override;

private:
    void PollSampleCb();
    void PollBusCb();

private:
    PublisherPtr<UDPCamMsgType> m_pubCamFrames;
    TimerSharedPtr              m_pull_timer;
    TimerSharedPtr              m_bus_timer;
    GstElement* m_pipeline = nullptr;
    GstElement* m_sink     = nullptr;
    GstBus*     m_bus      = nullptr;
};