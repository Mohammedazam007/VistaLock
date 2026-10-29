"""Frame voting: one blurry frame must not produce a wrong plate.
 
Reads for the same vehicle arrive over several frames. A session ends when no read has
arrived for `gap` seconds; the plate with the most confidence-weighted votes wins.
v1 assumes one vehicle at a time per camera lane (use --roi to restrict to the lane).
"""
from dataclasses import dataclass, replace
 
 
@dataclass
class VotedPlate:
    plate: str
    votes: int          # reads that agreed with the winner
    n_reads: int        # all reads in the session
    share: float        # winner's weight / total weight (0..1)
    first_seen: float
    last_seen: float
    best_conf: float
    track_id: int | None = None
 
 
class PlateVoter:
    def __init__(self, gap: float = 2.0, min_votes: int = 2, min_share: float = 0.5,
                 fuzzy_variants: bool = False):
        self.gap = gap
        self.min_votes = min_votes
        self.min_share = min_share
        self.fuzzy_variants = fuzzy_variants
        self._reads = []  # (plate, conf, ts)
 
    def add(self, plate: str, conf: float, ts: float):
        """Add a read. Returns a VotedPlate if this read started a new session and the
        previous one is now final and accepted, otherwise None."""
        finished = self.tick(ts)
        self._reads.append((plate, conf, ts))
        return finished
 
    def tick(self, ts: float):
        """Call with the current time on every frame so sessions close even with no reads."""
        if self._reads and ts - self._reads[-1][2] > self.gap:
            return self._finalize()
        return None
 
    def flush(self):
        return self._finalize() if self._reads else None
 
    def _finalize(self):
        reads, self._reads = self._reads, []
        weight, count, best = {}, {}, {}
        for plate, conf, _ in reads:
            weight[plate] = weight.get(plate, 0.0) + conf
            count[plate] = count.get(plate, 0) + 1
            best[plate] = max(best.get(plate, 0.0), conf)
        winner = max(weight, key=lambda p: (weight[p], count[p]))
        similar = {
            plate for plate in weight
            if self.fuzzy_variants and TrackVoteManager._same_plate_hypothesis(plate, winner)
        }
        similar.add(winner)
        cluster_weight = sum(weight[plate] for plate in similar)
        share = cluster_weight / sum(weight.values())
        if count[winner] < self.min_votes or share < self.min_share:
            return None
        times = [t for _, _, t in reads]
        return VotedPlate(winner, count[winner], len(reads), round(share, 3),
                          min(times), max(times), round(best[winner], 3))


class TrackVoteManager:
    """Keep independent OCR consensus clusters within each tracked plate box."""

    def __init__(self, gap: float = 2.0, min_votes: int = 2, min_share: float = 0.5):
        self.gap = gap
        self.min_votes = min_votes
        self.min_share = min_share
        self._voters = {}
        self._last_seen = {}
        self._plates = {}

    @staticmethod
    def _same_plate_hypothesis(a: str, b: str, max_edits: int = 2) -> bool:
        """Allow small OCR edits while separating distinct plate identities."""
        if abs(len(a) - len(b)) > max_edits:
            return False
        previous = list(range(len(b) + 1))
        for row, char_a in enumerate(a, start=1):
            current = [row]
            for col, char_b in enumerate(b, start=1):
                current.append(min(
                    current[-1] + 1,
                    previous[col] + 1,
                    previous[col - 1] + (char_a != char_b),
                ))
            if min(current) > max_edits:
                return False
            previous = current
        return previous[-1] <= max_edits

    def add(self, track_id: int, plate: str, conf: float, ts: float):
        """Add a read to its physical-track session and return completed sessions."""
        finished = self.tick(ts)
        voter = self._voters.get(track_id)
        hypotheses = self._plates.get(track_id, [])
        if voter is not None and not any(
            self._same_plate_hypothesis(plate, previous, max_edits=3)
            for previous in hypotheses
        ):
            result = voter.flush()
            if result is not None:
                finished.append(replace(result, track_id=track_id))
            voter = None
            hypotheses = []
        if voter is None:
            voter = self._voters[track_id] = PlateVoter(
                gap=self.gap, min_votes=self.min_votes, min_share=self.min_share,
                fuzzy_variants=True,
            )
            self._plates[track_id] = hypotheses
        hypotheses.append(plate)
        result = voter.add(plate, conf, ts)
        if result is not None:
            finished.append(replace(result, track_id=track_id))
        self._last_seen[track_id] = ts
        return finished

    def tick(self, ts: float):
        """Finalize each plate session after its own read gap expires."""
        finished = []
        for track_id, last_seen in list(self._last_seen.items()):
            if ts - last_seen > self.gap:
                result = self._voters.pop(track_id).flush()
                self._last_seen.pop(track_id)
                self._plates.pop(track_id)
                if result is not None:
                    finished.append(replace(result, track_id=track_id))
        return finished

    def flush(self):
        """Finalize all remaining plate sessions at end of input."""
        finished = []
        for track_id, voter in self._voters.items():
            result = voter.flush()
            if result is not None:
                finished.append(replace(result, track_id=track_id))
        self._voters.clear()
        self._last_seen.clear()
        self._plates.clear()
        return finished


class PlateBoxTracker:
    """Associate nearby plate boxes across sampled frames using IoU only."""

    def __init__(self, max_age: float = 1.0, min_iou: float = 0.4):
        self.max_age = max_age
        self.min_iou = min_iou
        self._tracks = {}
        self._next_id = 1

    @staticmethod
    def _iou(a, b):
        left = max(a[0], b[0])
        top = max(a[1], b[1])
        right = min(a[2], b[2])
        bottom = min(a[3], b[3])
        intersection = max(0, right - left) * max(0, bottom - top)
        area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
        area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        union = area_a + area_b - intersection
        return intersection / union if union else 0.0

    def assign(self, boxes, timestamp: float):
        """Return one stable ID per xyxy box; unmatched boxes start new tracks."""
        self._tracks = {
            track_id: track for track_id, track in self._tracks.items()
            if timestamp - track[1] <= self.max_age
        }
        pairs = []
        for track_id, track in self._tracks.items():
            previous = track[0]
            prev_w, prev_h = previous[2] - previous[0], previous[3] - previous[1]
            prev_cx, prev_cy = (previous[0] + previous[2]) / 2, (previous[1] + previous[3]) / 2
            for index, box in enumerate(boxes):
                iou = self._iou(box, previous)
                if iou >= self.min_iou:
                    pairs.append((1, iou, track_id, index))
                    continue

                width, height = box[2] - box[0], box[3] - box[1]
                if min(width, prev_w) <= 0 or min(height, prev_h) <= 0:
                    continue
                size_ratio = max(width / prev_w, prev_w / width,
                                 height / prev_h, prev_h / height)
                if size_ratio > 2.0:
                    continue

                center_x = (box[0] + box[2]) / 2
                center_y = (box[1] + box[3]) / 2
                distance = ((center_x - prev_cx) ** 2 + (center_y - prev_cy) ** 2) ** 0.5
                diagonal = max((prev_w ** 2 + prev_h ** 2) ** 0.5,
                               (width ** 2 + height ** 2) ** 0.5)
                normalized_distance = distance / diagonal
                if normalized_distance <= 1.5:
                    # IoU matches rank first; fallback pairs rank by proximity.
                    pairs.append((0, -normalized_distance, track_id, index))

        pairs.sort(reverse=True)
        ids = [None] * len(boxes)
        used_tracks = set()
        for _, _, track_id, index in pairs:
            if track_id in used_tracks or ids[index] is not None:
                continue
            ids[index] = track_id
            used_tracks.add(track_id)

        for index, box in enumerate(boxes):
            if ids[index] is None:
                ids[index] = self._next_id
                self._next_id += 1
            self._tracks[ids[index]] = (tuple(box), timestamp)
        return ids
