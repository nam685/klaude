from klaude.ui.status_bar import StatusBar


def test_quiet_status_bar_noop():
    """StatusBar with quiet=True should not activate."""
    bar = StatusBar(quiet=True)
    bar.start()
    assert not bar.is_active
    bar.update("test")
    bar.stop()


def test_default_status_bar_not_quiet():
    """StatusBar defaults to quiet=False."""
    bar = StatusBar()
    assert not bar._quiet
