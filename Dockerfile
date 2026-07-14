FROM python:3.10-slim

WORKDIR /app

# Concrete (Zama) compile son circuit FHE au démarrage et a besoin de l'éditeur de
# liens `ld` + d'un compilateur. On installe les outils de build indispensables.
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Faux module "torch" : Concrete l'importe pour un module de convolution qu'on n'utilise
# pas — on évite ainsi ~1 Go de dépendances (PyTorch + CUDA).
RUN mkdir -p /stub/torch && \
    printf 'class _D:\n    def __getattr__(self,n): return _D()\n    def __call__(self,*a,**k): return _D()\ndef __getattr__(name): return _D()\n' > /stub/torch/__init__.py

ENV PYTHONPATH=/stub \
    KADDU_CAPACITY=40 \
    KADDU_DB=/tmp/kaddu_zama.db \
    PYTHONUNBUFFERED=1

# Flask + le vrai moteur FHE de Zama (Concrete), sans PyTorch.
RUN pip install --no-cache-dir flask gunicorn "psycopg[binary]" && \
    pip install --no-cache-dir --no-deps concrete-python==2.11.0 && \
    pip install --no-cache-dir numpy scipy networkx z3-solver jsonpickle importlib_resources

COPY . /app

EXPOSE 7860

# 1 seul worker : les clés FHE sont générées une fois et partagées (indispensable).
# Forme "shell" pour lire $PORT (Render) avec repli 7860 (Hugging Face).
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-7860} --workers 1 --timeout 300 --preload
