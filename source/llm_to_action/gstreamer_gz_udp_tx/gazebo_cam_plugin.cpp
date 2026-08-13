#include "gazebo_cam_plugin.hpp"
#include "gazebo_cam_plugin_base.hpp"
#include <gz/sim/components/World.hh>
#include <gz/sim/components/Name.hh>
#include <gz/sim/Util.hh>
#include <gz/plugin/Register.hh>
#include <gst/gst.h>
#include <gst/app/gstappsrc.h>
#include <iostream>


namespace gazebo {


GstCameraPlugin::~GstCameraPlugin() {
    std::fprintf(stderr, 
        "[GAZEBO_UDP_CAMERA_PLUGIN_TX] Destroying Gazebo GstreamerCameraPlugin\n"
    );

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
    return;
}


void GstCameraPlugin::Configure(
    const gz::sim::Entity&                     entity,
    const std::shared_ptr<const sdf::Element>& sdf,
    gz::sim::EntityComponentManager&           entCompMgr,
    gz::sim::EventManager&                     evtMgr
) {
    std::fprintf(stderr, 
        "[GAZEBO_UDP_CAMERA_PLUGIN_TX] GStreamer UDP Camera Plugin Loaded!\n"
    );
    gst_init(nullptr, nullptr);

    /* For a singular drone & Default world => topic == dynamic_topic */
    std::string topic = "/world/default/model/x500_gimbal_0/link/camera_link/sensor/camera/image";
    gz::sim::Entity worldEntity = entCompMgr.EntityByComponents(gz::sim::components::World());
    std::string     worldName   = entCompMgr.Component<gz::sim::components::Name>(worldEntity)->Data();
    std::string     scoped      = gz::sim::scopedName(entity, entCompMgr, "/");
    std::string     dynamic_topic = "/world/" + worldName + "/" + scoped + "/image";

    std::fprintf(stderr, 
        "[GAZEBO_UDP_CAMERA_PLUGIN_TX] GStreamer Dynamically Hooked to %s ROS2-Gazebo Topic!\n",
        dynamic_topic.c_str()
    );
    this->m_node.Subscribe(dynamic_topic, &GstCameraPlugin::OnImageCb, this);
    return;
}


void GstCameraPlugin::InitializePipeline(guint w, guint h) {
    std::fprintf(stderr, 
        "[GAZEBO_UDP_CAMERA_PLUGIN_TX] Initializing Pipeline With camera dims (%u, %u)\n", w, h
    );
    m_pool = gst_buffer_pool_new();
    if(m_pool == nullptr) {
        std::fprintf(stderr, "[GAZEBO_UDP_CAMERA_PLUGIN_TX] memory-pool allocation from GStreamer failed\n");
        return;
    }

    m_frameSize = w * h * 3;
    GstStructure* config = gst_buffer_pool_get_config(m_pool);
    gst_buffer_pool_config_set_params(config, nullptr, m_frameSize, 60, 60); 
    gst_buffer_pool_set_config(m_pool, config);
    gst_buffer_pool_set_active(m_pool, TRUE);

    const std::string kGstPipelineDefStr = 
        "appsrc name=mysource format=time is-live=true "
        /* The gz camera sensor emits R8G8B8 (RGB, see gimbal model.sdf <format>). Declaring BGR here
           fed RGB bytes to gstreamer as BGR -> R/B swapped for the WHOLE pipeline (red person showed
           blue in the dashboard AND to the VLM, breaking colour disambiguation). Match the source: RGB. */
        "caps=video/x-raw,format=RGB,width=" + std::to_string(w) 
        + ",height="                         + std::to_string(h) 
        + ",framerate="                      + std::to_string(kOutCameraGStreamerFrameRate) + "/1 ! "
        "videoconvert ! "
        "video/x-raw,format=I420 ! " 
        "x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 ! " 
        /* 
            timestamp-offset=0 forces the RTP payload to be 0.
            we inject the correct simulation timestamp, 
            preventing random offsets from being written. 
        */
        "rtph264pay timestamp-offset=0 ! "
        "udpsink host=" + kUdpHostIpAddress + " port=" + std::to_string(kSitlUdpCamPort);

    m_pipeline  = gst_parse_launch(kGstPipelineDefStr.c_str(), nullptr);
    m_appSource = gst_bin_get_by_name(GST_BIN(m_pipeline), "mysource");
    gst_element_set_state(m_pipeline, GST_STATE_PLAYING);
    return;
}


void GstCameraPlugin::OnImageCb(const gz::msgs::Image& msg) {
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


} /* namespace Gazebo */


GZ_ADD_PLUGIN(gazebo::GstCameraPlugin, gz::sim::System, gazebo::GstCameraPlugin::ISystemConfigure)
GZ_ADD_PLUGIN_ALIAS(gazebo::GstCameraPlugin, "gazebo::GstCameraPlugin")
