"""_core.py is shared, file for file, with llama-index-readers-mesharc (llama_index/readers/mesharc/_core.py).

If this fails, _core.py was edited here only. Make the same change in the
other package, then update CORE_SHA256 in both copies of this test.
"""

import hashlib
import pathlib

import langchain_mesharc._core as core

CORE_SHA256 = "31dc9b1e036f42bafe633f7a9e5be4098cd154965eded9530f614a6f815a3922"


def test_core_matches_the_shared_copy():
    data = pathlib.Path(core.__file__).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == CORE_SHA256
