# SAM3 demo test suite

Generalized from the recognize.py logs. Each test pairs a demo image with its matched prompt
(faithful to the log) plus category-template variants, and runs SAM3 head-to-head against the
current Qwen3-VL pipeline. Definition: manifest.json (9 tests, 6 categories).

## Status

Blocked on inputs: the 9 image files are not yet on disk. Place them in
/root/models/vision/sam3-demo-frames/ with the names below (or tell me your names). Running the
suite needs a GPU slot (currently on hold by the owner).

## Tests

| id | image file | prompt | category |
|---|---|---|---|
| t1 | building_render.jpg | leftmost window, top floor | building-attribute |
| t2 | tower_damaged_bluetrim.jpg | top-most & left-most tower windows | building-attribute |
| t3 | two_buildings_people.jpg | all people + boilers (absent) | people + absent-object |
| t4 | man_tree_suit.jpg | bounding box around the person | camouflaged-person |
| t5 | cinema_audience.jpg | precise number of people | count |
| t6 | convoy_trucks.jpg | all people; notify weapon | people + weapon-notify |
| t7 | truck_armed_men.jpg | all people; notify weapon | people + weapon-notify |
| t8 | overhead_rpg.jpg | person aiming the weapon | weapon-notify |
| t9 | street_scene_ocr.png | windows, right building, middle floor | building-attribute |

## Method (per test)

SAM3 text-prompt -> boxes + masks vs the current pipeline (VLM boxes + SAM2 masks; the log is the
reference line where one exists). Report: detections, scores, latency; side-by-side overlays for
human review. Adversarial-absent parts (boilers) must return zero. No labeled ground truth, so the
owner reviews overlays. Runner lands here once the images and a GPU slot are available.
