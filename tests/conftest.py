"""Garante que `import waterweave` funcione ao rodar `pytest` sem configurar PYTHONPATH
manualmente — o pacote não está instalado em modo editável neste ambiente (mesmo padrão
já usado em cada página de `webapp/pages/*.py`)."""
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
