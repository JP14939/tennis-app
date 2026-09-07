# Retraining the fine-tuned ball detector

The ball detector is a single-class YOLO11n at
`data/10b_ball_detection/yolo_ball_run_v1/weights/best.pt`, loaded by
`racket_tracker.get_ball_model()`. `data/10b_ball_detection/` is gitignored and
transferred to the server by hand.

## Recipe

```powershell
cd scripts
.\venv\Scripts\activate

# 1. Pull the real hand-drawn labels from the hosted server (the local
#    manual_ball_label_log.jsonl is an 18-row stub -- prepare_ball_yolo_dataset
#    now rejects anything under 100 rows).
#    scp root@<server>:.../manual_ball_label_log.jsonl \
#        ../data/10b_ball_detection/manual_ball_label_log_server.jsonl

# 2. (optional) label + review the wide-court / far-ball frames first:
python sample_wide_court_ball_frames.py
python label_wide_court_ball_frames.py         # Haiku confirm; then hand-review
#    -> wide_court_ball_labels.jsonl  (+ _handlabeled.jsonl)

# 3. Build the YOLO dataset. Split is by CLIP (analysis id), not frame; the
#    output dir is wiped every run. Pass every label log you want merged:
python prepare_ball_yolo_dataset.py \
    ../data/10b_ball_detection/manual_ball_label_log_server.jsonl \
    ../data/10b_ball_detection/wide_court_ball_labels.jsonl \
    ../data/10b_ball_detection/wide_court_ball_labels_handlabeled.jsonl
#    -> data/10b_ball_detection/yolo_dataset_v1/{images,labels}/{train,val} + data.yaml
#    asserts train/val image AND clip-id disjointness before it finishes.

# 4. Back up the current run, then train (~1.8 hr on CPU).
cp -r ../data/10b_ball_detection/yolo_ball_run_v1\
      ../data/10b_ball_detection/yolo_ball_run_v1_BACKUP_$(date +%Y%m%d_%H%M%S)
python train_ball_detector.py                  # imgsz 480, multi_scale, scale 0.6

# 5. Check it actually moved the needle BEFORE trusting best.pt:
python audit_finetuned_ball_confidence.py      # at-contact detection rate / conf
python calibrate_ball_inference_scale.py       # imgsz sweep, regimes A/A2/B
python eval_near_court_ball_detection.py        # near/far split, regime C
```

## Gates

- `audit_finetuned_ball_confidence.py` at-contact detection rate **>=** the
  current 93.3% (avg conf 0.557).
- `calibrate_ball_inference_scale.py` regime B `detect_rate` up, especially
  **backhand** (currently 0.77, weakest everywhere), with `fp_rate` not up.
- `eval_near_court_ball_detection.py` near-side regime C `detect_rate` and
  `mean_iou` up, negative `fp_rate` flat.
- The dataset build's leakage assertions pass (they now run automatically).

If a gate fails, restore `yolo_ball_run_v1/` from the backup -- the shipped
`best.pt` is whatever `get_ball_model()` loads, so a bad train that overwrites
in place (`exist_ok=True`) silently degrades production until reverted.

## Known history

- v1 was trained on ~312 positives, **all ~28x29px near-player balls**; only
  ~22 wide-court positives, Claude-confirmed not hand-drawn. It has never been
  shown a genuine wide/far ball as a positive -- hence imgsz 480 + multi_scale
  and the wide-court labels above.
- Pre-2026-09-07, `prepare_ball_yolo_dataset.py` split by frame and never
  cleaned its output dir -> 76 images in both train and val. Both fixed.
- 5 clips / 16 labels were static decoys (a ball on the ground boxed instead
  of the one in play), Jack-confirmed 2026-08-25;
  `find_fully_static_files()` excludes them automatically.
