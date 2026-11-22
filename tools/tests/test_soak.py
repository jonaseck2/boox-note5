from booxctl.soak import touch_ok


def test_touch_ok_needs_enabled_irq_and_power_on():
    assert touch_ok("Driver interrupt is ENABLED\non\n")
    assert not touch_ok("Driver interrupt is DISABLED\non\n")
    assert not touch_ok("Driver interrupt is ENABLED\noff\n")
    assert not touch_ok("")
