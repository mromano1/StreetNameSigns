import subprocess

import pipeline_shell as shell


class FakeCompletedProcess:
    def __init__(self, returncode):
        self.returncode = returncode


def test_run_step_raises_systemexit_with_the_subprocess_own_exit_code(monkeypatch):
    # Propagates the underlying command's own exit code via SystemExit(int)
    # -- not a string, which Python's SystemExit always maps to exit status
    # 1 regardless of the original code (see run_step's own docstring).
    monkeypatch.setattr(subprocess, "run", lambda command: FakeCompletedProcess(returncode=3))
    try:
        shell.run_step(["some_script.py"])
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 3


def test_run_step_does_not_raise_when_the_subprocess_succeeds(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda command: FakeCompletedProcess(returncode=0))
    shell.run_step(["some_script.py"])  # no exception
