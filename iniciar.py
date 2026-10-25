"""Iniciador portátil: usa .deps, .venv ou o Python instalado."""
from pathlib import Path
import os
import socket
import subprocess
import sys
import time
import webbrowser

root = Path(__file__).resolve().parent
os.chdir(root)
python = root / ".venv" / "Scripts" / "python.exe"
if not python.exists():
    python = Path(sys.executable)
port = None
for candidate in range(8050, 8061):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", candidate))
            port = candidate
            break
        except OSError:
            continue
if port is None:
    raise SystemExit("As portas 8050 a 8060 estão ocupadas. Encerre instâncias anteriores.")
process = subprocess.Popen([str(python), str(root / "app.py"), "--port", str(port)], cwd=root)
try:
    for _ in range(120):
        if process.poll() is not None:
            raise SystemExit("O painel não iniciou. Confira as dependências e o erro acima.")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.25):
                webbrowser.open(f"http://127.0.0.1:{port}")
                break
        except OSError:
            time.sleep(.25)
    print("Mantenha esta janela aberta. Use Ctrl+C para encerrar o simulador.")
    process.wait()
except KeyboardInterrupt:
    process.terminate()
    process.wait(timeout=10)
