#include <gz/sim/System.hh>
#include <gz/sim/components/World.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/Util.hh>
#include <gz/plugin/Register.hh>
#include <gz/transport/Node.hh>
#include <gz/msgs/image.pb.h>
#include <gst/gst.h>
#include <gst/app/gstappsrc.h>
#include <iostream>


namespace gazebo {


class GstCameraPlugin : 
    public gz::sim::System,
    public gz::sim::ISystemConfigure 
{
public:
    ~GstCameraPlugin() override {
        std::cerr << "[STATUS] Destroying GstCameraPlugin...\n";
        if (m_pool) {
            gst_buffer_pool_set_active(m_pool, FALSE);
            gst_object_unref(m_pool);
        }
        if (m_appSource) {
            gst_object_unref(m_appSource);
        }
        if (m_pipeline) {
            gst_element_set_state(m_pipeline, GST_STATE_NULL);
            gst_object_unref(m_pipeline);
        }
    }


    void Configure(
        const gz::sim::Entity&                     entity,
        const std::shared_ptr<const sdf::Element>& sdf,
        gz::sim::EntityComponentManager&           ecm,
        gz::sim::EventManager&                     eventManager
    ) override {
        std::cerr << "[STATUS] ZERO-COPY PLUGIN LOADED\n";
        gst_init(nullptr, nullptr);
        std::string topic = "/world/default/model/x500_gimbal_0/link/camera_link/sensor/camera/image";
        
        gz::sim::Entity worldEntity = ecm.EntityByComponents(gz::sim::components::World());
        std::string     worldName   = ecm.Component<gz::sim::components::Name>(worldEntity)->Data();
        std::string     scoped      = gz::sim::scopedName(entity, ecm, "/");
        std::string     dynamic_topic = "/world/" + worldName + "/" + scoped + "/image";

        std::cerr << "[STATUS] GStreamer hooked dynamically to: " << dynamic_topic << "\n";
        this->m_node.Subscribe(dynamic_topic, &GstCameraPlugin::OnImageCb, this);
        return;
    }


private:
    void InitializePipeline(guint w, guint h) {
        std::cerr << "[STATUS] Initializing Pipeline: " << w << "x" << h << "\n";
        m_frameSize = w * h * 3;

        m_pool = gst_buffer_pool_new();
        GstStructure* config = gst_buffer_pool_get_config(m_pool);
        gst_buffer_pool_config_set_params(config, nullptr, m_frameSize, 60, 60); 
        gst_buffer_pool_set_config(m_pool, config);
        gst_buffer_pool_set_active(m_pool, TRUE);

        std::string pipeline_str = 
            "appsrc name=mysource format=time is-live=true "
            "caps=video/x-raw,format=BGR,width=" + std::to_string(w) + ",height=" + std::to_string(h) + ",framerate=30/1 ! "
            "videoconvert ! "
            "video/x-raw,format=I420 ! " 
            "x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 ! " 
            /* 
                timestamp-offset=0 forces the RTP payload to be 0.
                we inject the correct simulation timestamp, 
                preventing random offsets from being written. 
            */
            "rtph264pay timestamp-offset=0 ! "
            "udpsink host=127.0.0.1 port=11111";

        m_pipeline  = gst_parse_launch(pipeline_str.c_str(), nullptr);
        m_appSource = gst_bin_get_by_name(GST_BIN(m_pipeline), "mysource");
        gst_element_set_state(m_pipeline, GST_STATE_PLAYING);
        return;
    }


    void OnImageCb(const gz::msgs::Image& msg) {
        // std::cerr << "[STATUS] CALLBACK RECEIVED!!!\n";
        GstBufferPoolAcquireParams params;
        GstBuffer*    buffer = nullptr;
        GstFlowReturn ret;
        GstMapInfo    map;
        guint w = msg.width();
        guint h = msg.height();
        gsize actual_size = w * h * 3;
        const guint64 kSec = msg.header().stamp().sec();
        const guint64 kNanoSec = msg.header().stamp().nsec();
        const guint64 kTimestamp_ns = (kSec * 1000000000ULL) + kNanoSec;

        if (!m_pipeline) {
            InitializePipeline(w, h);
        }

        if (actual_size != m_frameSize) {
            std::cerr << "Frame size changed. Dropping.\n";
            return;
        }

        params.format = GST_FORMAT_UNDEFINED;
        params.start = -1;
        params.stop = -1;
        params.flags = GST_BUFFER_POOL_ACQUIRE_FLAG_DONTWAIT;
        ret = gst_buffer_pool_acquire_buffer(m_pool, &buffer, &params);
        if (ret != GST_FLOW_OK) {
            return;
        }

        /* Map the buffer we just retrieved*/
        gst_buffer_map(buffer, &map, GST_MAP_WRITE);
        std::memcpy(map.data, msg.data().c_str(), m_frameSize);
        gst_buffer_unmap(buffer, &map);

        /* Inject The simulation time into the gstreamer buffer manually */
        GST_BUFFER_PTS(buffer) = kTimestamp_ns;
        GST_BUFFER_DTS(buffer) = kTimestamp_ns;

        gst_buffer_set_size(buffer, m_frameSize);
        gst_app_src_push_buffer(GST_APP_SRC(m_appSource), buffer);
        return;
    }


private:
    gz::transport::Node m_node;
    GstBufferPool*      m_pool      = nullptr;
    GstElement*         m_pipeline  = nullptr;
    GstElement*         m_appSource = nullptr;
    gsize               m_frameSize = 0;
};


} /* namespace Gazebo */

GZ_ADD_PLUGIN(gazebo::GstCameraPlugin, gz::sim::System, gazebo::GstCameraPlugin::ISystemConfigure)
GZ_ADD_PLUGIN_ALIAS(gazebo::GstCameraPlugin, "gazebo::GstCameraPlugin")