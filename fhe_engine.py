"""Moteur de vote confidentiel avec le VRAI chiffrement FHE de Zama (Concrete)."""
import os, sys, types

# Stub torch : Concrete l'importe pour un module de convolution qu'on n'utilise pas.
if "torch" not in sys.modules:
    try:
        import torch  # noqa
    except Exception:
        _m = types.ModuleType("torch")
        class _D:
            def __getattr__(self, n): return _D()
            def __call__(self, *a, **k): return _D()
        _m.__getattr__ = lambda name: _D()
        sys.modules["torch"] = _m

from concrete import fhe

K = int(os.environ.get("KADDU_CAPACITY", "30"))   # nb max de votants par vote
_names = [f"v{i}" for i in range(K)]
_src = "def _t(" + ",".join(_names) + "): return " + "+".join(_names)
_g = {}; exec(_src, _g)
_circuit = fhe.Compiler(_g["_t"], {n: "encrypted" for n in _names}).compile(
    [tuple([0]*K), tuple([1]*K)])
_circuit.keygen()

_zero = {}
def _z(slot):
    if slot not in _zero:
        a = [None]*K; a[slot] = 0
        _zero[slot] = _circuit.encrypt(*a)[slot]
    return _zero[slot]

def capacity(): return K

def encrypt_ballot(slot, bit):
    a = [None]*K; a[slot] = int(bit)
    return _circuit.encrypt(*a)[slot].serialize()

def tally(blobs):
    cts = [fhe.Value.deserialize(b) for b in blobs]
    for i in range(len(blobs), K):
        cts.append(_z(i))
    return int(_circuit.decrypt(_circuit.run(*cts)))
