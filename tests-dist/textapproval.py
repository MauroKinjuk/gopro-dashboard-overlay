import inspect
import sys
from functools import wraps
from pathlib import Path

import pytest


def approve_text(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        function_name = f.__name__
        sourcefile = Path(inspect.getfile(f))

        approval_dir = sourcefile.parents[0].joinpath("approvals")

        approval_stem = f"{sourcefile.stem}_{function_name.replace('test_', '')}"
        approved_location = approval_dir.joinpath(f"{approval_stem}.approved.txt")
        actual_location = approval_dir.joinpath(f"{approval_stem}.actual.txt")

        actual_text = f(*args, **kwargs)

        if actual_text is None:
            raise AssertionError(f"{function_name} needs to return some text")

        actual_location.write_text(actual_text)

        if approved_location.exists():
            approved_text = approved_location.read_text()

            if not actual_text == approved_text:
                print(f"If this is OK....", file=sys.stderr)
                print(f"cp {actual_location} {approved_location}", file=sys.stderr)
                raise AssertionError("Actual and Approved do not match")
        else:
            print(f"cp {actual_location} {approved_location}", file=sys.stderr)
            pytest.xfail(f"{function_name}: approved File does not exist, no assertion")
    return wrapper