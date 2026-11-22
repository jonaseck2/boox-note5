from booxctl.watch import INTERESTING, new_dirs


def test_new_dirs_only_unpulled_stamps():
    listing = "20261122-101500\n20261122-090000\n.last\njunk\n"
    assert new_dirs(listing, {"20261122-090000"}) == ["20261122-101500"]


def test_interesting_keeps_crashes_drops_noise():
    assert INTERESTING.search("11-22 10:00:01.000 F/libc ( 812): Fatal signal 11 (SIGSEGV)")
    assert INTERESTING.search("I/boox ( 600): libbooxepdc: skip update nfb=2")
    assert not INTERESTING.search("D/Chromium( 999): tile raster done")


def test_interesting_keeps_touch_recovery():
    assert INTERESTING.search("11-22 15:00:01.000 I/boox-touch( 600): touch dead (DISABLED / off), driver rebound")
