from voting import PlateBoxTracker, PlateVoter, TrackVoteManager
 
 
def test_majority_beats_one_bad_frame():
    v = PlateVoter()
    for i, (p, c) in enumerate([("TS09AB1234", .9), ("TS09AB1284", .4), ("TS09AB1234", .8), ("TS09AB1234", .85)]):
        v.add(p, c, i * 0.1)
    out = v.flush()
    assert out.plate == "TS09AB1234" and out.votes == 3 and out.n_reads == 4
 
 
def test_single_read_is_rejected():
    v = PlateVoter(min_votes=2)
    v.add("TS09AB1234", .95, 0.0)
    assert v.flush() is None
 
 
def test_split_vote_is_rejected():
    v = PlateVoter(min_votes=2, min_share=0.6)
    for i, p in enumerate(["TS09AB1234", "TS09AB1235", "TS09AB1234", "TS09AB1235"]):
        v.add(p, .8, i * 0.1)
    assert v.flush() is None
 
 
def test_gap_separates_two_vehicles():
    v = PlateVoter(gap=2.0)
    done = []
    for t in (0.0, 0.2, 0.4):
        done.append(v.add("TS09AB1234", .9, t))
    for t in (5.0, 5.2, 5.4):
        done.append(v.add("KA01A1234", .9, t))
    done.append(v.flush())
    plates = [d.plate for d in done if d]
    assert plates == ["TS09AB1234", "KA01A1234"]
 
 
def test_tick_closes_session_without_new_reads():
    v = PlateVoter(gap=2.0)
    v.add("TS09AB1234", .9, 0.0)
    v.add("TS09AB1234", .9, 0.3)
    assert v.tick(1.0) is None
    assert v.tick(3.0).plate == "TS09AB1234"


def test_track_vote_manager_finalizes_repeated_identical_reads():
    manager = TrackVoteManager(min_votes=2)
    manager.add(12, "TS07JH0122", 0.40, 3.00)
    manager.add(12, "TS07JH0122", 0.42, 3.17)

    results = manager.flush()
    assert len(results) == 1
    assert results[0].plate == "TS07JH0122"
    assert results[0].votes == results[0].n_reads == 2
    assert results[0].track_id == 12


def test_track_vote_manager_keeps_interleaved_vehicles_independent():
    # Interleaved OCR reads for different tracked vehicles must not dilute votes.
    observations = [
        (1, "TS07JY6282", .58, 2.17),
        (1, "TS07JY6282", .72, 2.33),
        (1, "TS07JY6282", .91, 2.50),
        (1, "TS07JI6282", .43, 2.67),
        (2, "TS07JH0122", .40, 3.00),
        (2, "TS07JH0122", .42, 3.17),
        (3, "TS15FC5179", .38, 4.33),
        (3, "TS15FC5479", .68, 4.50),
        (3, "TS15FC5479", .81, 4.67),
        (3, "TS15FC5479", .56, 4.83),
    ]
    manager = TrackVoteManager(gap=2.0, min_votes=2, min_share=0.5)
    original_voter = PlateVoter(gap=2.0, min_votes=2, min_share=0.5)
    results = []

    for track_id, plate, confidence, timestamp in observations:
        results.extend(manager.add(track_id, plate, confidence, timestamp))
        original_voter.add(plate, confidence, timestamp)

    assert original_voter.flush() is None
    results.extend(manager.flush())
    by_track = {result.track_id: result for result in results}
    assert {track_id: result.plate for track_id, result in by_track.items()} == {
        1: "TS07JY6282", 2: "TS07JH0122", 3: "TS15FC5479"
    }
    assert by_track[1].votes == 3
    assert by_track[2].votes == 2
    assert by_track[3].votes == 3


def test_track_vote_manager_combines_ocr_variants_without_cross_vehicle_votes():
    manager = TrackVoteManager(min_votes=2, min_share=0.5)
    manager.add(7, "TS08HJO7071", .37, 3.25)
    manager.add(7, "TS08HIJ0707", .70, 3.33)
    manager.add(8, "TS08HJ0702", .31, 3.42)
    manager.add(7, "TS08HJ0707", .43, 3.50)
    manager.add(7, "TS08HJO7071", .31, 3.58)
    manager.add(7, "TS08HJ0707", .37, 3.75)

    results = manager.flush()
    assert len(results) == 1
    assert results[0].track_id == 7
    assert results[0].plate == "TS08HJ0707"
    assert results[0].votes == 2
    assert results[0].n_reads == 5
    assert results[0].share == 1.0


def test_track_vote_manager_splits_distinct_plates_reused_by_box_track():
    manager = TrackVoteManager(min_votes=2)
    manager.add(11, "UK04M212", .40, 1.83)
    manager.add(11, "UK04M212", .42, 1.92)
    completed = manager.add(11, "TS07JH0122", .40, 3.00)
    manager.add(11, "TS07JH0122", .42, 3.17)

    assert len(completed) == 1
    assert completed[0].plate == "UK04M212"
    assert completed[0].track_id == 11
    results = manager.flush()
    assert len(results) == 1
    assert results[0].plate == "TS07JH0122"


def test_plate_hypothesis_similarity_accepts_ocr_edits_but_separates_vehicles():
    same = TrackVoteManager._same_plate_hypothesis
    assert same("TS08HIJ0707", "TS08HJ0707")
    assert same("TS07JH0422", "TS07JH0122")
    assert not same("TS07JY6282", "TS07JH0122")
    assert not same("TS08HJ0707", "TS15FC5479")


def test_track_vote_manager_still_requires_two_exact_plate_reads():
    manager = TrackVoteManager(min_votes=2)
    manager.add(5, "TS09AB1234", .90, 1.0)
    manager.add(5, "TS09AB1235", .90, 1.1)
    assert manager.flush() == []


def test_track_vote_manager_preserves_timestamps_and_flushes_at_eof():
    manager = TrackVoteManager(min_votes=2)
    manager.add(4, "TS07JH0122", .40, 3.00)
    manager.add(4, "TS07JH0122", .42, 3.17)

    result, = manager.flush()
    assert (result.first_seen, result.last_seen) == (3.00, 3.17)
    assert manager.flush() == []


def test_plate_box_tracker_keeps_two_spatially_separate_vehicles_distinct():
    tracker = PlateBoxTracker(max_age=1.0, min_iou=0.1)
    first = tracker.assign([(10, 10, 50, 25), (200, 10, 240, 25)], 0.0)
    moved = tracker.assign([(12, 10, 52, 25), (198, 10, 238, 25)], 0.1)

    assert first == [1, 2]
    assert moved == [1, 2]


def test_plate_box_tracker_expires_old_tracks_without_reusing_ids():
    tracker = PlateBoxTracker(max_age=0.5, min_iou=0.1)
    first = tracker.assign([(10, 10, 50, 25)], 0.0)
    after_gap = tracker.assign([(10, 10, 50, 25)], 0.6)

    assert first == [1]
    assert after_gap == [2]


def test_plate_box_tracker_associates_fast_motion_without_overlap():
    tracker = PlateBoxTracker(max_age=1.0, min_iou=0.4)
    first = tracker.assign([(81, 1193, 183, 1247)], 0.0)
    moved = tracker.assign([(61, 1101, 161, 1157)], 0.167)
    moved_again = tracker.assign([(41, 970, 141, 1020)], 0.333)

    assert first == moved == moved_again == [1]


def test_plate_box_tracker_does_not_join_nearby_vehicles_that_keep_iou_tracks():
    tracker = PlateBoxTracker(max_age=1.0, min_iou=0.4)
    first = tracker.assign([(10, 10, 110, 60), (145, 10, 245, 60)], 0.0)
    moved = tracker.assign([(12, 10, 112, 60), (143, 10, 243, 60)], 0.1)

    assert first == [1, 2]
    assert moved == [1, 2]
