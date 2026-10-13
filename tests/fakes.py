import subprocess


class FakeRunner:
    """Stands in for subprocess.run: maps a command prefix to (returncode, stdout)."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, args, timeout=None):
        self.calls.append(list(args))
        for prefix, (code, out) in self.table.items():
            if list(args[: len(prefix)]) == list(prefix):
                return subprocess.CompletedProcess(args, code, out, "")
        raise AssertionError(f"unexpected command: {args}")
