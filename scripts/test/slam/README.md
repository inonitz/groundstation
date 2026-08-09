# slam — stella_vslam SITL bring-up (spec B1)

Answers one question with a number: **does stella_vslam actually track in SITL?**

## Build first

The SLAM node is not in the normal build. It has its own tree and its own option.

```bash
cmake -S . -B build/release/slam -G Ninja \
    -DGROUNDSTATION_BUILD_SLAM=ON \
    -DGROUNDSTATION_BUILD_EXECUTABLE=OFF \
    -DGROUNDSTATION_BUILD_TESTS=OFF \
    -DGROUNDSTATION_BUILD_BENCHMARKS=OFF \
    -DGROUNDSTATION_BUILD_BACKEND_PX4=ON \
    -DBUILD_SHARED_LIBS=1 \
    -DCMAKE_BUILD_TYPE=Release \
    -DGIT_SUBMODULE=ON
cmake --build build/release/slam --target stella_vslam_monocular -j"$(nproc)"
```

A backend option is required even though nothing here uses it. The top-level
`CMakeLists.txt` fails configuration when no backend is selected.

## Run

```bash
cd scripts/test/slam
./run.sh
```

`run.sh` brings up the normal SITL stack through `lib/sim_core.sh`, then grafts on
two extra tmux panes: the SLAM node, and the comparator. It flies `--canned-cross`
in `rubicon_targets`, which is textured enough for monocular tracking to
initialise. `default_car` and `empty` are not.

The comparator's output also lands in `slam_check.log`.

## Reading the output

One line per second:

```
[SLAM_CHECK] rate=29.80hz tracking_frac=0.99 drift_m=0.14 drift_max_m=0.31 \
             spread_ratio=0.97 pairs=340 scale=7.081 frames=30 note=ok
```

| field | meaning | healthy |
| --- | --- | --- |
| `rate` | slam/pose publish rate | near the camera's 30 Hz |
| `tracking_frac` | poses published per camera frame | above ~0.5, ideally near 1.0 |
| `drift_m` | horizontal RMSE against EKF2, after similarity alignment | small and steady |
| `spread_ratio` | aligned SLAM extent over true extent | near 1.0 |
| `scale` | recovered metric scale | steady, not drifting toward 0 |
| `note` | `ok`, or why the number is not trustworthy | `ok` |

Ctrl-C prints a `[SLAM_CHECK_SUMMARY]` verdict line and exits non-zero on FAIL.

### Why drift alone is not enough

Monocular SLAM has no metric scale and no fixed world origin, so the comparator
fits a similarity transform (scale, rotation, translation) before measuring. That
fit has a trap: if the SLAM track is mostly noise, the cheapest fit shrinks it
onto a point, and drift then saturates at the size of the flight path rather than
growing. `spread_ratio` is the guard. A collapsed fit reads near 0 and is
reported as `note=collapsed-fit`, which fails the run even though `drift_m` looks
small.

## What a human still has to check

The comparator covers tracking quality. The map itself needs one look in rviz:

- **Landmarks** should roughly trace the visible geometry of the world, not sit
  in a random scatter.
- **The trajectory line** should be roughly smooth and match the commanded cross,
  not jagged, and not frozen at one point.
- **The pose arrow** should move continuously, with no sudden large jumps between
  frames.

Topics to add in rviz: `slam/pose` (Pose), `slam/active_cloud_pts` and
`slam/local_cloud_pts` (PointCloud2). Fixed frame is `map`.
