#include <gz/sim/System.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/details/image.pb.h>
#include <gst/gst.h>


namespace gazebo {


class GstCameraPlugin : 
    public gz::sim::System,
    public gz::sim::ISystemConfigure 
{
public:
    ~GstCameraPlugin() override;
    void Configure(
        const gz::sim::Entity&                     entity,
        const std::shared_ptr<const sdf::Element>& sdf,
        gz::sim::EntityComponentManager&           entCompMgr,
        gz::sim::EventManager&                     evtMgr
    ) override;


private:
    void InitializePipeline(guint w, guint h);
    void OnImageCb(const gz::msgs::Image& msg);


private:
    gz::transport::Node m_node;
    GstBufferPool*      m_pool      = nullptr;
    GstElement*         m_pipeline  = nullptr;
    GstElement*         m_appSource = nullptr;
    gsize               m_frameSize = 0;
};


} /* namespace Gazebo */
