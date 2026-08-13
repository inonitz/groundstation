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
#include <opencv2/imgproc.hpp>   /* cv::rectangle/putText -- annotated-frame overlay (A2). */
#include "perception/target_tracker.hpp"  /* TargetTracker / TrackedSnapshot / stable ids. */
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
    /* onAnnotatedFrame / onDepthColormap are A2 observability sinks (fmu owns the ROS
       publishers). Default-empty so existing callers/tests that pass neither still
       compile and simply skip publishing -- purely additive, no behavior change. */
    PerceptionRuntime(const std::string& segModelPath, const std::string& depthModelPath,
                       int segThreads, int depthThreads, u32 segLoopMs, u32 depthLoopMs,
                       std::function<khUDPCamMsgType()> frameSource,
                       std::function<void(cv::Mat const&)> onAnnotatedFrame = {},
                       std::function<void(cv::Mat const&)> onDepthColormap  = {})
        : m_seg(segModelPath, segThreads)
        , m_depth(depthModelPath, depthThreads)
        , m_frameSource(std::move(frameSource))
        , m_onAnnotatedFrame(std::move(onAnnotatedFrame))
        , m_onDepthColormap(std::move(onDepthColormap))
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
        auto t = std::atomic_load(&m_tracked);
        if (!t) return nullptr;
        /* aliasing shared_ptr: shares t's lifetime but points at the inner snap, so every
           existing caller is unchanged and gets the snapshot with a matched lifetime. */
        return std::shared_ptr<PerceptionSnapshot>(t, &t->snap);
    }
    /* snap + per-detection stable ids together, for id-aware callers ([PERCEPTION]/verbs). */
    std::shared_ptr<TrackedSnapshot> trackedSnapshot() const {
        return std::atomic_load(&m_tracked);
    }

    /* Perception refresh rate: raw seg/depth loop iteration counts (one per processed frame). The
       FMU deltas these ~1 Hz to report seg/depth Hz on /fmu/rates -- the real inference throughput,
       distinct from the throttled ~10 Hz publish rate. */
    u64 segIters()   const { return m_segIters.load(std::memory_order_relaxed); }
    u64 depthIters() const { return m_depthIters.load(std::memory_order_relaxed); }

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
        auto tracked = std::make_shared<TrackedSnapshot>();
        tracked->snap = snap;
        u64 t = snap.host_stamp_us ? snap.host_stamp_us : nowUs();
        tracked->ids = trackerUpdate(m_tracker, tracked->snap, t, m_trackerParams);
        std::atomic_store(&m_tracked, tracked);
    }

    /* Median metric depth (cm) over an arbitrary pixel rect of the latest dense depth map. For a
       VLM-emitted bbox on a target YOLO cannot class (house/window): the depth net covers every
       pixel, so we sample it directly, no detection needed. Same median-over-bbox sampling as
       medianDepthCm(), rect-only (no seg mask). rect is in native camera pixels. Returns 0.0f when
       there is no depth map yet, the rect falls off-frame, or every sample is invalid. */
    float medianDepthCmInRect(cv::Rect const& rect) const {
        std::shared_ptr<cv::Mat> depth = std::atomic_load(&m_depthMap);
        if (!depth || depth->empty()) return 0.0f;
        cv::Rect bbox = rect & cv::Rect(0, 0, depth->cols, depth->rows);
        if (bbox.width <= 0 || bbox.height <= 0) return 0.0f;
        std::vector<float> samples;
        samples.reserve(static_cast<size_t>(bbox.width) * static_cast<size_t>(bbox.height));
        for (int y = bbox.y; y < bbox.y + bbox.height; ++y) {
            const float* row = depth->ptr<float>(y);
            for (int x = bbox.x; x < bbox.x + bbox.width; ++x) {
                float v = row[x];
                if (v > 0.0f && std::isfinite(v)) samples.push_back(v);
            }
        }
        if (samples.empty()) return 0.0f;
        std::sort(samples.begin(), samples.end());
        return samples[samples.size() / 2] * 100.0f;
    }

    /* Bearing (errX in -1..1) + metric range (m) of the nearest large structure in the central band
       of the dense depth map. For a VISUAL-SERVO orbit of a non-COCO structure (a building) YOLO
       cannot box: tracked directly from depth every tick, so the orbit needs no fixed 3-D centre
       (monocular RANGE is too noisy to place one). Robust -- a 10th-percentile "near" threshold plus a
       column-centroid of the near shell, so speckle and far background do not pull the bearing.
       false when too few near samples (nothing solid in view). cx = image centre x (px). */
    bool nearestStructure(float cx, float& outErrX, float& outRangeM) const {
        std::shared_ptr<cv::Mat> depth = std::atomic_load(&m_depthMap);
        if (!depth || depth->empty()) return false;
        const int W = depth->cols, H = depth->rows;
        const int x0 = static_cast<int>(W * 0.10f), x1 = static_cast<int>(W * 0.90f);
        const int y0 = static_cast<int>(H * 0.30f), y1 = static_cast<int>(H * 0.70f);
        std::vector<float> vals; vals.reserve(static_cast<size_t>((x1 - x0) * (y1 - y0)));
        for (int y = y0; y < y1; ++y) {
            const float* r = depth->ptr<float>(y);
            for (int x = x0; x < x1; ++x) { float v = r[x]; if (v > 0.0f && std::isfinite(v)) vals.push_back(v); }
        }
        if (vals.size() < 300) return false;
        std::vector<float> srt = vals; std::sort(srt.begin(), srt.end());
        const float pNear = srt[srt.size() / 10];
        const float band  = pNear + 2.5f;
        double colSum = 0.0, dSum = 0.0; long n = 0;
        for (int y = y0; y < y1; ++y) {
            const float* r = depth->ptr<float>(y);
            for (int x = x0; x < x1; ++x) { float v = r[x];
                if (v > 0.0f && std::isfinite(v) && v <= band) { colSum += x; dSum += v; ++n; } }
        }
        if (n < 150) return false;
        outErrX   = (static_cast<float>(colSum / static_cast<double>(n)) - cx) / cx;
        outRangeM = static_cast<float>(dSum / static_cast<double>(n));
        return true;
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
                    m_segIters.fetch_add(1, std::memory_order_relaxed);
                    publish(dets);
                    /* A2: hand the FMU an already-annotated frame to publish. The fixed
                       void(cv::Mat const&) callback cannot carry the detections, so the
                       boxes/labels are drawn here where dets is in scope, on a clone (the
                       toCvShare mat aliases the ROS message and must not be written). */
                    if (m_onAnnotatedFrame) {
                        auto tr = std::atomic_load(&m_tracked);
                        m_onAnnotatedFrame(drawDetections(frame, dets, tr ? &tr->ids : nullptr));
                    }
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
                    m_depthIters.fetch_add(1, std::memory_order_relaxed);
                    /* A2: emit the raw metric-depth mat; the FMU normalizes + applyColorMap. */
                    if (m_onDepthColormap) m_onDepthColormap(*depth);
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
        auto tracked = std::make_shared<TrackedSnapshot>();
        PerceptionSnapshot& snap = tracked->snap;
        u32  n    = std::min(static_cast<u32>(dets.size()), PerceptionSnapshot::kMaxDetections);

        for (u32 i = 0; i < n; ++i) {
            const vision::SegDetection& d   = dets[i];
            TargetDetection&            out = snap.dets[i];
            std::snprintf(out.label, sizeof(FixedStringType), "%s", vision::coco_class_name(d.classId));
            out.bbox_xmin      = d.box.x;
            out.bbox_ymin      = d.box.y;
            out.bbox_xmax      = d.box.x + d.box.width;
            out.bbox_ymax      = d.box.y + d.box.height;
            out.confidence     = d.conf;
            out.median_depth_cm = (depth && !depth->empty()) ? medianDepthCm(*depth, d) : 0.0f;
        }
        snap.count       = n;
        snap.host_stamp_us = nowUs();
        snap.valid       = true;
        /* Stable ids: run the tracker on this frame's boxes, published in lockstep with the snap. */
        tracked->ids = trackerUpdate(m_tracker, snap, snap.host_stamp_us, m_trackerParams);
        std::atomic_store(&m_tracked, tracked);
    }

    /* A2 observability: draw YOLO boxes + class@conf labels onto a clone of the frame,
       for the annotated-frame topic the FMU publishes. Clone because the source mat
       aliases the ROS image message (toCvShare) and must stay read-only. */
    static cv::Mat drawDetections(const cv::Mat& frame,
                                   const std::vector<vision::SegDetection>& dets,
                                   FrameTrackIds const* ids) {
        cv::Mat out = frame.clone();
        char    label[80];
        u32     i = 0;
        for (const vision::SegDetection& d : dets) {
            cv::rectangle(out, d.box, cv::Scalar(0, 255, 0), 2);
            if (ids && i < ids->count)
                std::snprintf(label, sizeof(label), "#%d %s %.0f%%",
                    ids->id[i], vision::coco_class_name(d.classId), d.conf * 100.0f);
            else
                std::snprintf(label, sizeof(label), "%s %.0f%%",
                    vision::coco_class_name(d.classId), d.conf * 100.0f);
            cv::putText(out, label, cv::Point(d.box.x, std::max(0, d.box.y - 5)),
                cv::FONT_HERSHEY_SIMPLEX, 0.5, cv::Scalar(0, 255, 0), 1);
            ++i;
        }
        return out;
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
    std::function<void(cv::Mat const&)> m_onAnnotatedFrame; /* A2: annotated-frame sink (fmu publishes). */
    std::function<void(cv::Mat const&)> m_onDepthColormap;  /* A2: raw depth-mat sink (fmu colormaps).   */
    std::chrono::milliseconds         m_segPeriod;
    std::chrono::milliseconds         m_depthPeriod;

    std::thread       m_segThread;
    std::thread       m_depthThread;
    std::atomic<bool> m_running{false};

    std::shared_ptr<cv::Mat>            m_depthMap; /* latest metric depth map, meters. */
    std::shared_ptr<TrackedSnapshot> m_tracked; /* snap + stable ids, published atomically to the FMU. */
    TargetTracker m_tracker;                    /* frame-to-frame identity (seg thread is sole writer). */
    TrackerParams m_trackerParams{0.3f, 80.0f, 15u};   /* iouGate, distGatePx, coast frames. Coast is
                                                          bumped from 5: live actor detection flickers,
                                                          and a short window churned track_ids (13->50->86). */
    std::atomic<float> m_nearestFreeDepthM{0.0f};   /* central-cone near-depth (m), 0 = unknown.  */
    std::atomic<u64>   m_freeDepthStampUs{0};       /* depth cycle time of the reading above.     */
    std::atomic<u64>   m_segIters{0};                /* seg loop iterations (perception refresh).  */
    std::atomic<u64>   m_depthIters{0};              /* depth loop iterations.                     */

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
