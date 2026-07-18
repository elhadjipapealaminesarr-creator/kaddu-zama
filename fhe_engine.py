"""Moteur de vote confidentiel avec le VRAI chiffrement FHE de Zama (Concrete).

Optimisé pour l'hébergement gratuit (Render, 512 Mo) :
- l'import est INSTANTANÉ (aucune compilation au démarrage) ;
- le circuit FHE est compilé + les clés générées UNE SEULE FOIS, à la
  première utilisation réelle (premier vote ou première clôture) ;
- `capacity()` ne déclenche aucun calcul (les pages restent rapides).
Ainsi le serveur web démarre tout de suite (health-check OK) et ne sature
plus la mémoire au boot.
"""
import os
import sys
import types

# Nombre max de votants par vote (ajustable sans toucher au code).
K = int(os.environ.get("KADDU_CAPACITY", "30"))

_circuit = None      # circuit FHE compilé (construit à la demande)
_zero = {}           # cache des zéros chiffrés par slot


def _stub_torch():
    """Concrete importe torch pour un module qu'on n'utilise pas : on le neutralise."""
    if "torch" in sys.modules:
        return
    try:
        import torch  # noqa: F401
    except Exception:
        _m = types.ModuleType("torch")

        class _D:
            def __getattr__(self, n):
                return _D()

            def __call__(self, *a, **k):
                return _D()

        _m.__getattr__ = lambda name: _D()
        sys.modules["torch"] = _m


def _ensure():
    """Compile le circuit FHE et génère les clés — une seule fois, à la demande."""
    global _circuit
    if _circuit is not None:
        return _circuit
    _stub_torch()
    from concrete import fhe
    names = ["v%d" % i for i in range(K)]
    src = "def _t(" + ",".join(names) + "): return " + "+".join(names)
    g = {}
    exec(src, g)
    circuit = fhe.Compiler(
        g["_t"], {n: "encrypted" for n in names}
    ).compile([tuple([0] * K), tuple([1] * K)])
    circuit.keygen()
    _circuit = circuit
    return _circuit


def capacity():
    """Instantané : ne compile rien."""
    return K


def _z(slot):
    if slot not in _zero:
        c = _ensure()
        a = [None] * K
        a[slot] = 0
        _zero[slot] = c.encrypt(*a)[slot]
    return _zero[slot]


def encrypt_ballot(slot, bit):
    c = _ensure()
    a = [None] * K
    a[slot] = int(bit)
    return c.encrypt(*a)[slot].serialize()


def tally(blobs):
    from concrete import fhe
    c = _ensure()
    cts = [fhe.Value.deserialize(b) for b in blobs]
    for i in range(len(blobs), K):
        cts.append(_z(i))
    return int(c.decrypt(c.run(*cts)))
