from voting import PlateVoter
 
 
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