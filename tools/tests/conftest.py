import pytest
from booxctl.runner import Result


class FakeRunner:
    """Records argv; returns scripted outputs keyed by a substring of the joined argv."""

    def __init__(self):
        self.calls = []
        self.envs = []
        self.script = []  # list of (substring, Result)

    def on(self, substring, stdout=b"", returncode=0, stderr=b""):
        self.script.append((substring, Result(returncode, stdout, stderr)))
        return self

    def run(self, argv, *, input=None, timeout=120, env=None):
        self.calls.append(list(argv))
        self.envs.append(env)
        joined = " ".join(argv)
        for sub, res in self.script:
            if sub in joined:
                return res
        return Result(0, b"", b"")


@pytest.fixture
def fake():
    return FakeRunner()


@pytest.fixture(autouse=True)
def _boox_serial(monkeypatch):
    monkeypatch.setenv("BOOX_SERIAL", "TESTSERIAL1")
