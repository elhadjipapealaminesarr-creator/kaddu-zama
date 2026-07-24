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


# ---------------------------------------------------------------------------
# Mise en commun protégée : somme homomorphe de VALEURS (pas juste des bits).
# Circuit isolé du vote : compilé séparément, à la première utilisation. Une
# éventuelle erreur ici n'affecte donc jamais le vote ni les autres modules.
# ---------------------------------------------------------------------------

# Valeur max qu'un participant peut mettre en commun (FCFA). Règle la largeur
# de bits du circuit. 1 000 000 par défaut : pic mémoire ~230 Mo, OK sur Render.
POOL_MAX = int(os.environ.get("KADDU_POOL_MAX", "1000000"))

_pool_circuit = None      # circuit de somme d'entiers (construit à la demande)
_pool_zero = {}           # cache des zéros chiffrés par slot


def _ensure_pool():
    """Compile le circuit de somme d'entiers + clés — une seule fois, à la demande."""
    global _pool_circuit
    if _pool_circuit is not None:
        return _pool_circuit
    _stub_torch()
    from concrete import fhe
    names = ["v%d" % i for i in range(K)]
    src = "def _s(" + ",".join(names) + "): return " + "+".join(names)
    g = {}
    exec(src, g)
    circuit = fhe.Compiler(
        g["_s"], {n: "encrypted" for n in names}
    ).compile([tuple([0] * K), tuple([POOL_MAX] * K)])
    circuit.keygen()
    _pool_circuit = circuit
    return _pool_circuit


def _pz(slot):
    if slot not in _pool_zero:
        c = _ensure_pool()
        a = [None] * K
        a[slot] = 0
        _pool_zero[slot] = c.encrypt(*a)[slot]
    return _pool_zero[slot]


def pool_max():
    """Instantané : ne compile rien."""
    return POOL_MAX


def encrypt_value(slot, value):
    """Chiffre la valeur d'un participant dans son slot. La valeur en clair
    n'est jamais stockée : seul ce chiffré l'est."""
    v = max(0, min(int(value), POOL_MAX))
    c = _ensure_pool()
    a = [None] * K
    a[slot] = v
    return c.encrypt(*a)[slot].serialize()


def pool_sum(blobs):
    """Additionne les valeurs chiffrées et ne révèle QUE le total."""
    from concrete import fhe
    c = _ensure_pool()
    cts = [fhe.Value.deserialize(b) for b in blobs]
    for i in range(len(blobs), K):
        cts.append(_pz(i))
    return int(c.decrypt(c.run(*cts)))


# ---------------------------------------------------------------------------
# Coffre-fort d'alertes : RÉVÉLATION À SEUIL.
# On additionne des bits chiffrés (1 alerte = 1 bit), puis une table univariée
# ne laisse passer le compte QUE s'il atteint le seuil ; sinon elle renvoie 0.
# Conséquence : sous le seuil, le déchiffrement rend 0 — zéro information, pas
# même « il existe 1 alerte ». Le signaleur isolé est mathématiquement protégé.
# Le seuil est figé dans le circuit (ce n'est pas un secret) ; un circuit est
# compilé et mis en cache par valeur de seuil. Circuit isolé des autres modules.
# ---------------------------------------------------------------------------

_thr_circuits = {}   # seuil -> circuit compilé
_thr_zero = {}       # (seuil, slot) -> zéro chiffré


# Nombre max de circuits de seuil gardés en mémoire simultanément. Chaque circuit
# pèse ~sa clé FHE ; sur le tier gratuit (512 Mo) on borne pour éviter le SIGKILL.
_THR_CACHE_MAX = int(os.environ.get("KADDU_THR_CACHE", "2"))


def _ensure_thr(threshold):
    t = int(threshold)
    if t in _thr_circuits:
        return _thr_circuits[t]
    # Cache borné : si plein, on évacue le plus ancien (et ses zéros) pour libérer
    # la mémoire avant de compiler un nouveau circuit.
    if len(_thr_circuits) >= _THR_CACHE_MAX:
        oldest = next(iter(_thr_circuits))
        _thr_circuits.pop(oldest, None)
        for key in [k for k in _thr_zero if k[0] == oldest]:
            _thr_zero.pop(key, None)
    _stub_torch()
    from concrete import fhe
    names = ["v%d" % i for i in range(K)]
    # s = somme des bits ; table univariée : s si s >= seuil, sinon 0.
    body = ("def _f(%s):\n"
            "  s = %s\n"
            "  return __import__('concrete').fhe.univariate(lambda x: x if x >= %d else 0)(s)"
            ) % (",".join(names), "+".join(names), t)
    g = {}
    exec(body, g)
    circuit = fhe.Compiler(
        g["_f"], {n: "encrypted" for n in names}
    ).compile([tuple([0] * K), tuple([1] * K)])
    circuit.keygen()
    _thr_circuits[t] = circuit
    return circuit


def _tz(threshold, slot):
    key = (int(threshold), slot)
    if key not in _thr_zero:
        c = _ensure_thr(threshold)
        a = [None] * K
        a[slot] = 0
        _thr_zero[key] = c.encrypt(*a)[slot]
    return _thr_zero[key]


def encrypt_alert(threshold, slot, bit):
    """Chiffre une alerte (1 bit) sous le circuit du seuil donné."""
    c = _ensure_thr(threshold)
    a = [None] * K
    a[slot] = int(bit)
    return c.encrypt(*a)[slot].serialize()


def alert_reveal(threshold, blobs):
    """Renvoie le nombre d'alertes concordantes SI le seuil est atteint, sinon 0.
    Le calcul (somme + seuil) se fait entièrement sur les chiffrés."""
    from concrete import fhe
    c = _ensure_thr(threshold)
    cts = [fhe.Value.deserialize(b) for b in blobs]
    for i in range(len(blobs), K):
        cts.append(_tz(threshold, i))
    return int(c.decrypt(c.run(*cts)))
