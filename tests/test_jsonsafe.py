import json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
import jsonsafe


class _FakeScalar:
    def __init__(self, v):
        self._v = v

    def item(self):
        return self._v


def test_scalar_via_item():
    assert jsonsafe.json_default(_FakeScalar(True)) is True
    assert jsonsafe.json_default(_FakeScalar(0.5)) == 0.5


def test_array_via_tolist():
    class _FakeArr:
        def tolist(self):
            return [1, 2]
    assert jsonsafe.json_default(_FakeArr()) == [1, 2]


def test_unknown_type_raises():
    try:
        jsonsafe.json_default(object())
    except TypeError:
        return
    assert False, "expected TypeError for an unsupported type"


def test_numpy_roundtrip_if_available():
    try:
        import numpy as np
    except ImportError:
        return
    obj = {"b": np.bool_(True), "f": np.float64(0.5), "i": np.int64(3),
           "arr": np.array([1.0, 2.0])}
    restored = json.loads(json.dumps(obj, default=jsonsafe.json_default))
    assert restored == {"b": True, "f": 0.5, "i": 3, "arr": [1.0, 2.0]}
