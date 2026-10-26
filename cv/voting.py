"""Frame voting: one blurry frame must not produce a wrong plate.
 
Reads for the same vehicle arrive over several frames. A session ends when no read has
arrived for `gap` seconds; the plate with the most confidence-weighted votes wins.
v1 assumes one vehicle at a time per camera lane (use --roi to restrict to the lane).
"""
from dataclasses import dataclass
 
 
@dataclass
class VotedPlate:
    plate: str
    votes: int          # reads that agreed with the winner
    n_reads: int        # all reads in the session
    share: float        # winner's weight / total weight (0..1)
    first_seen: float
    last_seen: float
    best_conf: float
 
 
class PlateVoter:
    def __init__(self, gap: float = 2.0, min_votes: int = 2, min_share: float = 0.5):
        self.gap = gap
        self.min_votes = min_votes
        self.min_share = min_share
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
        share = weight[winner] / sum(weight.values())
        if count[winner] < self.min_votes or share < self.min_share:
            return None
        times = [t for _, _, t in reads]
        return VotedPlate(winner, count[winner], len(reads), round(share, 3),
                          min(times), max(times), round(best[winner], 3))
 