#pragma once
/*
   PerceptionRuntime -- owns the two vision-lib engines and publishes an
   atomic PerceptionSnapshot the control/VLM path reads (ARCH sec 9).

   Two-rate by design (docs/ROADMAP.md 4.1.8): on this class of CPU the depth
   model measures ~3x over its real-time target while segmentation meets its
   target, so the two run as independent, differently-paced loops instead of
   one blocking call. This is why vision::fuse() (which runs both models
   back-to-back in a single call) is deliberately NOT used here -- calling it
   in a loop would force segmentation to wait on depth every cycle and
   collapse the two rates back into one. Both engine calls used
   (segment()/estimate()) are public vision-lib API; nothing in
   /root/build_yolo is modified.

   Consequence accepted per ROADMAP 4.1.8a: label/bbox refresh near the seg
   rate, median_depth_cm can lag behind the current bbox by up to one depth
   cycle. Block 6.1's emergency boundary must tolerate that staleness.
*/
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <functional>
#include <memory>
#include <string>
#include <thread>
#include <vector>

#include <opencv2/core.hpp>
#include <cv_bridge/cv_bridge.hpp>
#include <cstdio>            /* fprintf/stderr -- approach-real perception debug */

#include <util2/C/base_type.h>
#include <vision/perception_types.hpp>
#include <vision/yolo_seg_engine.hpp>
#include <vision/yolo_depth_engine.hpp>
#include <vision/coco_labels.hpp>

#include "gstreamer_udp_cam_rx/rx_node_base.hpp" /* khUDPCamMsgType */

class PerceptionRuntime {
public:
    PerceptionRuntime(const std::string& segModelPath, const std::string& depthModelPath,
                       int segThreads, int depthThreads, u32 segLoopMs, u32 depthLoopMs,
                       std::function<khUDPCamMsgType()> frameSource)
        : m_seg(segModelPath, segThreads)
        , m_depth(depthModelPath, depthThreads)
        , m_frameSource(std::move(frameSource))
        , m_segPeriod(segLoopMs)
        , m_depthPeriod(depthLoopMs)
    {}

    ~PerceptionRuntime() { stop(); }

    PerceptionRuntime(const PerceptionRuntime&) = delete;
    PerceptionRuntime& operator=(const PerceptionRuntime&) = delete;

    void start() {
        if (m_running.exchange(true, std::memory_order_acq_rel)) return;
        m_segThread   = std::thread(&PerceptionRuntime::segLoop, this);
        m_depthThread = std::thread(&PerceptionRuntime::depthLoop, this);
    }

    void stop() {
        if (!m_running.exchange(false, std::memory_order_acq_rel)) return;
        if (m_segThread.joinable())   m_segThread.join();
        if (m_depthThread.joinable()) m_depthThread.join();
    }

    /* Same atomic-shared_ptr idiom the FMU already uses for m_currImg. */
    std::shared_ptr<PerceptionSnapshot> snapshot() const {
        return std::atomic_load(&m_snapshot);
    }

    /* Nearest free-space depth (m) over a central forward cone of the whole depth map -- the
       obstacle signal the per-detection medians cannot give (a wall has no YOLO box). 0.0f = unknown
       (no valid samples yet). *stampUs (if non-null) gets the depth cycle time so the caller can
       treat a stale reading as unknown, the same way it gates the snapshot age. */
    float nearestFreeDepthM(u64* stampUs = nullptr) const {
        if (stampUs) *stampUs = m_freeDepthStampUs.load(std::memory_order_relaxed);
        return m_nearestFreeDepthM.load(std::memory_order_relaxed);
    }

    /* Both ONNX engines loaded their model. The FMU aborts startup if this is false:
       a missing/mispathed model must fail LOUD, not silently emit zero detections
       (a wrong path once cost hours of "why does approach never see anything"). */
    bool ready() const { return m_seg.ok() && m_depth.ok(); }

    /* Test-only: publish a synthesized snapshot through the same atomic path the real seg
       loop uses. Safe to call even while the real engines are running -- if the vision
       models aren't loaded (engine.ok() == false, e.g. no models mounted), the real loops
       never call publish(), so this is the only writer and nothing races it. Used by the
       canned APPROACH rig (ROADMAP 5.1 verification, no YOLO needed). */
    void injectSynthetic(PerceptionSnapshot const& snap) {
        std::atomic_store(&m_snapshot, std::make_shared<PerceptionSnapshot>(snap));
    }

private:
    void segLoop() {
        while (m_running.load(std::memory_order_relaxed)) {
            auto tickStart = std::chrono::steady_clock::now();
            khUDPCamMsgType img = m_frameSource();
            if (img && m_seg.ok()) {
                cv::Mat frame = cv_bridge::toCvShare(img, "bgr8")->image;
                if (!frame.empty()) {
                    std::vector<vision::SegDetection> dets = m_seg.segment(frame, kConf, kIou);
                    publish(dets);
                }
            }
            sleepRemainder(tickStart, m_segPeriod);
        }
    }

    void depthLoop() {
        while (m_running.load(std::memory_order_relaxed)) {
            auto tickStart = std::chrono::steady_clock::now();
            khUDPCamMsgType img = m_frameSource();
            if (img && m_depth.ok()) {
                cv::Mat frame = cv_bridge::toCvShare(img, "bgr8")->image;
                if (!frame.empty()) {
                    auto depth = std::make_shared<cv::Mat>(m_depth.estimate(frame));
                    m_nearestFreeDepthM.store(computeNearestFreeDepthM(*depth), std::memory_order_relaxed);
                    m_freeDepthStampUs.store(nowUs(), std::memory_order_relaxed);
                    std::atomic_store(&m_depthMap, depth);
                }
            }
            sleepRemainder(tickStart, m_depthPeriod);
        }
    }

    void publish(const std::vector<vision::SegDetection>& dets) {
        std::shared_ptr<cv::Mat> depth = std::atomic_load(&m_depthMap);
        auto snap = std::make_shared<PerceptionSnapshot>();
        u32  n    = std::min(static_cast<u32>(dets.size()), PerceptionSnapshot::kMaxDetections);

        for (u32 i = 0; i < n; ++i) {
            const vision::SegDetection& d   = dets[i];
            TargetDetection&            out = snap->dets[i];
            std::snprintf(out.label, sizeof(FixedStringType), "%s", vision::coco_class_name(d.classId));
            out.bbox_xmin      = d.box.x;
            out.bbox_ymin      = d.box.y;
            out.bbox_xmax      = d.box.x + d.box.width;
            out.bbox_ymax      = d.box.y + d.box.height;
            out.confidence     = d.conf;
            out.median_depth_cm = (depth && !depth->empty()) ? medianDepthCm(*depth, d) : 0.0f;
        }
        snap->count       = n;
        snap->host_stamp_us = nowUs();
        snap->valid       = true;
        std::atomic_store(&m_snapshot, snap);
    }

    /* Same bbox/mask median-over-depth sampling as vision::fuse()'s internal
       medianDepthMeters() (perception_fusion.cpp) -- reimplemented here, not
       imported, because splitting seg/depth onto separate rates means we
       fuse across two independently-timed engine calls, not one fuse() call
       on a single frame. Public inputs only (cv::Rect/cv::Mat), no lib
       internals touched. */
    static float medianDepthCm(const cv::Mat& depth, const vision::SegDetection& det) {
        cv::Rect bbox = det.box & cv::Rect(0, 0, depth.cols, depth.rows);
        if (bbox.width <= 0 || bbox.height <= 0) return 0.0f;

        std::vector<float> samples;
        samples.reserve(static_cast<size_t>(bbox.width) * static_cast<size_t>(bbox.height));
        const bool useMask = !det.mask.empty() && det.mask.size() == depth.size() &&
                              det.mask.type() == CV_8UC1;

        for (int y = bbox.y; y < bbox.y + bbox.height; ++y) {
            const float* depthRow = depth.ptr<float>(y);
            const uchar* maskRow  = useMask ? det.mask.ptr<uchar>(y) : nullptr;
            for (int x = bbox.x; x < bbox.x + bbox.width; ++x) {
                if (useMask && maskRow[x] == 0) continue;
                float v = depthRow[x];
                if (v > 0.0f && std::isfinite(v)) samples.push_back(v);
            }
        }
        if (samples.empty()) return 0.0f;
        std::sort(samples.begin(), samples.end());
        return samples[samples.size() / 2] * 100.0f;
    }

    /* Nearest obstacle depth (m) over a central forward cone of the depth map -- for the emergency
       boundary, which must stop for ANY geometry, not just YOLO-boxed objects (a wall gives no
       detection). The cone is a central band biased ABOVE the lower frame so level forward flight
       does not read the ground as an obstacle. A low percentile (not the raw min) is used so a few
       speckle pixels cannot trip it -- a real close surface fills a good fraction of the cone.
       Returns 0.0f (unknown) if too few valid samples. Cone/percentile are first guesses -- sweep
       in SITL against the forward/cross/terrain tests, which must NOT false-trip on ground ahead. */
    static float computeNearestFreeDepthM(const cv::Mat& depth) {
        if (depth.empty()) return 0.0f;
        int x0 = static_cast<int>(depth.cols * kFreeConeXLo);
        int x1 = static_cast<int>(depth.cols * kFreeConeXHi);
        int y0 = static_cast<int>(depth.rows * kFreeConeYLo);
        int y1 = static_cast<int>(depth.rows * kFreeConeYHi);
        std::vector<float> samples;
        samples.reserve(static_cast<size_t>(std::max(0, x1 - x0)) *
                        static_cast<size_t>(std::max(0, y1 - y0)));
        for (int y = y0; y < y1; ++y) {
            const float* row = depth.ptr<float>(y);
            for (int x = x0; x < x1; ++x) {
                float v = row[x];
                if (v > 0.0f && std::isfinite(v)) samples.push_back(v);
            }
        }
        if (samples.size() < kFreeConeMinSamples) return 0.0f;
        size_t k = static_cast<size_t>(samples.size() * kFreeConePercentile);
        if (k >= samples.size()) k = samples.size() - 1;
        std::nth_element(samples.begin(), samples.begin() + k, samples.end());
        return samples[k];
    }

    static void sleepRemainder(std::chrono::steady_clock::time_point tickStart,
                                std::chrono::milliseconds period) {
        auto elapsed = std::chrono::steady_clock::now() - tickStart;
        if (elapsed < period) std::this_thread::sleep_for(period - elapsed);
    }

    static u64 nowUs() {
        return static_cast<u64>(std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
    }

    vision::YoloSegEngine             m_seg;
    vision::YoloDepthEngine           m_depth;
    std::function<khUDPCamMsgType()>  m_frameSource;
    std::chrono::milliseconds         m_segPeriod;
    std::chrono::milliseconds         m_depthPeriod;

    std::thread       m_segThread;
    std::thread       m_depthThread;
    std::atomic<bool> m_running{false};

    std::shared_ptr<cv::Mat>            m_depthMap; /* latest metric depth map, meters. */
    std::shared_ptr<PerceptionSnapshot> m_snapshot; /* published atomically to the FMU. */
    std::atomic<float> m_nearestFreeDepthM{0.0f};   /* central-cone near-depth (m), 0 = unknown.  */
    std::atomic<u64>   m_freeDepthStampUs{0};       /* depth cycle time of the reading above.     */

    static constexpr float kConf = 0.25f;
    static constexpr float kIou  = 0.45f;

    /* Free-space cone (fractions of frame) for computeNearestFreeDepthM. Central band, biased above
       the lower frame so level forward flight does not sample the ground. Low percentile + a
       min-sample floor reject speckle. First guesses -- sweep in SITL (see the helper comment). */
    static constexpr float  kFreeConeXLo = 0.35f;
    static constexpr float  kFreeConeXHi = 0.65f;
    static constexpr float  kFreeConeYLo = 0.28f;
    static constexpr float  kFreeConeYHi = 0.55f;
    static constexpr float  kFreeConePercentile = 0.05f;  /* ~nearest, robust to a few speckle pixels. */
    static constexpr size_t kFreeConeMinSamples = 200;    /* fewer valid pixels than this -> unknown.   */
};
