import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from campeonatos import buscar_todos_campeonatos
import json

c = buscar_todos_campeonatos(force_update=False)
print('Total campeonatos:', len(c))
print(json.dumps(c[:50], ensure_ascii=False, indent=2))
