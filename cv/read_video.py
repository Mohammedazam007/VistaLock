
"""VistaLock: YOLO plate detection + EasyOCR + frame voting."""

import argparse
import json
import os
import sys
import time

import cv2
import easyocr
from ultralytics import YOLO

from plate_utils import best_candidate_from_ocr_variants, is_valid_plate
from voting import PlateBoxTracker, TrackVoteManager

DEFAULT_MODEL = "models/best.pt"
ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Video path or webcam index, e.g. 0")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--every", type=int, default=5,
                        help="Process every Nth frame (default: 5)")
    parser.add_argument("--det-conf", type=float, default=0.25,
                        help="Minimum YOLO detection confidence")
    parser.add_argument("--min-conf", type=float, default=0.30,
                        help="Minimum OCR box confidence")
    parser.add_argument("--gap", type=float, default=2.0)
    parser.add_argument("--min-votes", type=int, default=2)
    parser.add_argument("--roi", help="Optional x,y,w,h region")
    parser.add_argument("--crops-dir", default="output/plate_crops")
    parser.add_argument("--out", default="output/reads.jsonl")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.every < 1:
        parser.error("--every must be at least 1")
    if args.min_votes < 1:
        parser.error("--min-votes must be at least 1")
    if not 0 <= args.det_conf <= 1 or not 0 <= args.min_conf <= 1:
        parser.error("Confidence thresholds must be between 0 and 1")

    return args


def main():
    args = parse_args()
    source = int(args.source) if args.source.isdigit() else args.source

    roi = None
    if args.roi:
        try:
            roi = tuple(int(v.strip()) for v in args.roi.split(","))
            if len(roi) != 4 or roi[2] <= 0 or roi[3] <= 0:
                raise ValueError
        except ValueError:
            sys.exit("--roi must be x,y,w,h with positive width and height")

    detector = YOLO(args.model)
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        sys.exit(f"Cannot open source: {args.source}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25.0

    os.makedirs(args.crops_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    voter = TrackVoteManager(gap=args.gap, min_votes=args.min_votes)
    box_tracker = PlateBoxTracker()
    best_frame = {}
    results = []
    frame_idx = 0
    ocr_frames = 0
    start = time.time()

    # Each run starts a fresh result file.
    with open(args.out, "w", encoding="utf-8") as file:
        pass

    def emit(voted):
        if voted is None:
            return

        track_id = voted.track_id
        best = best_frame.pop((track_id, voted.plate), None)
        image_path = None

        if best is not None:
            _, crop = best
            image_path = os.path.join(
                args.crops_dir,
                f"{voted.plate}_{int(voted.first_seen * 1000)}.jpg",
            )
            cv2.imwrite(image_path, crop)

        record = {
            "plate": voted.plate,
            "track_id": track_id,
            "votes": voted.votes,
            "reads": voted.n_reads,
            "share": voted.share,
            "first_seen_s": round(voted.first_seen, 2),
            "last_seen_s": round(voted.last_seen, 2),
            "best_conf": voted.best_conf,
            "image": image_path,
        }
        results.append(record)
        print("PLATE", json.dumps(record))

        with open(args.out, "a", encoding="utf-8") as file:
            file.write(json.dumps(record) + "\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            timestamp = frame_idx / fps
            view = frame

            if roi:
                x, y, w, h = roi
                x1, y1 = max(0, x), max(0, y)
                x2, y2 = min(frame.shape[1], x + w), min(frame.shape[0], y + h)
                if x1 >= x2 or y1 >= y2:
                    raise ValueError("ROI lies outside the video frame")
                view = frame[y1:y2, x1:x2]

            for voted in voter.tick(timestamp):
                emit(voted)

            if frame_idx % args.every == 0:
                detections = detector.predict(
                    view,
                    imgsz=640,
                    conf=args.det_conf,
                    verbose=False,
                    device="cpu",
                )[0]
                ocr_frames += 1

                boxes = list(detections.boxes)
                box_coords = [box.xyxy[0].tolist() for box in boxes]
                track_ids = box_tracker.assign(box_coords, timestamp)
                for box, track_id in zip(boxes, track_ids):
                    bx1, by1, bx2, by2 = (
                        int(v) for v in box.xyxy[0].tolist()
                    )
                    bx1 = max(0, bx1)
                    by1 = max(0, by1)
                    bx2 = min(view.shape[1], bx2)
                    by2 = min(view.shape[0], by2)

                    if bx2 <= bx1 or by2 <= by1:
                        continue

                    crop = view[by1:by2, bx1:bx2]
                    if crop.size == 0:
                        continue

                    # Pad tight detector boxes, then compare two OCR scales.
                    pad_x = max(2, int(crop.shape[1] * 0.06))
                    pad_y = max(2, int(crop.shape[0] * 0.12))
                    padded = cv2.copyMakeBorder(
                        crop, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_REPLICATE,
                    )
                    ocr_variants = []
                    for scale in (2, 3):
                        enlarged = cv2.resize(
                            padded, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_CUBIC,
                        )
                        ocr_variants.append(reader.readtext(
                            enlarged,
                            allowlist=ALLOWLIST,
                            detail=1,
                            paragraph=False,
                        ))

                    candidate = best_candidate_from_ocr_variants(
                        ocr_variants, args.min_conf
                    )
                    if candidate is None:
                        continue
                    plate, confidence = candidate
                    if not is_valid_plate(plate):
                        continue

                    if args.verbose:
                        print(
                            f"  t={timestamp:6.2f}s "
                            f"plate={plate} OCR={confidence:.2f} "
                            f"YOLO={float(box.conf[0]):.2f}"
                        )

                    crop_key = (track_id, plate)
                    previous = best_frame.get(crop_key)
                    if previous is None or confidence > previous[0]:
                        best_frame[crop_key] = (confidence, crop.copy())

                    for voted in voter.add(int(track_id), plate, float(confidence), timestamp):
                        emit(voted)

            if args.show:
                preview = view.copy()
                for box in detections.boxes if frame_idx % args.every == 0 else []:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imshow("VistaLock - YOLO plate detection", preview)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            frame_idx += 1

        for voted in voter.flush():
            emit(voted)

    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()

    elapsed = time.time() - start
    print(
        f"\n{len(results)} vehicle(s) finalized | {frame_idx} frames, "
        f"{ocr_frames} sampled | {elapsed:.1f}s total"
    )
    print(f"Results: {args.out}")


if __name__ == "__main__":
    main()
