import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime
import re
from typing import Dict, List, Optional

CACHE_DIR = 'cache'
CACHE_FILE = os.path.join(CACHE_DIR, 'campeonatos.json')
os.makedirs(CACHE_DIR, exist_ok=True)

TIMEOUT = 8
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def gerar_slug(texto: str) -> str:
    """Gera slug normalizado a partir de texto"""
    t = (texto or '').lower().strip()
    t = re.sub(r'[^a-z0-9]+', '-', t)
    t = t.strip('-')
    return t[:100] if t else 'campeonato-' + datetime.now().strftime('%Y%m%d%H%M%S')


def extrair_campeonato(jogo: str, nome: str, data: str, link: str, 
                       source_link: Optional[str] = None) -> Dict:
    """Retorna campeonato em formato padronizado"""
    return {
        'jogo': jogo,
        'nome': nome or 'Sem título',
        'data': data or '',
        'link': link or '',
        'source_link': source_link or link or '',
        'slug': gerar_slug(nome)
    }


def buscar_campeonatos_vlr() -> List[Dict]:
    """Busca campeonatos do VLR.gg (Valorant)"""
    url = 'https://www.vlr.gg/events'
    eventos = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for item in soup.select('a.event-item')[:15]:  # Limita a 15 para performance
            try:
                titulo = item.select_one('.event-item-title')
                if not titulo:
                    continue
                nome = titulo.get_text(strip=True)
                
                # Extrai data
                data = ''
                for desc in item.select('.event-item-desc-item'):
                    label = desc.select_one('.event-item-desc-item-label')
                    if label and 'date' in label.get_text(strip=True).lower():
                        data = desc.get_text(strip=True)
                        break
                
                link = item.get('href', '')
                if link and link.startswith('/'):
                    link = 'https://www.vlr.gg' + link
                
                if nome and link:
                    evento = extrair_campeonato('Valorant', nome, data, link, link)
                    eventos.append(evento)
            except Exception:
                continue
    except Exception as e:
        print(f"Erro ao buscar VLR: {e}")
    
    return eventos

def buscar_campeonatos_lol() -> List[Dict]:
    """Busca campeonatos de League of Legends"""
    url = 'https://lolesports.com/schedule'
    campeonatos = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for item in soup.select('.event-item-wrapper')[:15]:  # Limita a 15
            try:
                nome_elem = item.select_one('.match-series-title')
                nome = nome_elem.get_text(strip=True) if nome_elem else ''
                
                data_elem = item.select_one('.match-item-datetime')
                data = data_elem.get_text(strip=True) if data_elem else ''
                
                link_elem = item.select_one('a')
                link = link_elem.get('href', '') if link_elem else ''
                if link and link.startswith('/'):
                    link = 'https://lolesports.com' + link
                
                if nome and link:
                    evento = extrair_campeonato('League of Legends', nome, data, link, link)
                    campeonatos.append(evento)
            except Exception:
                continue
    except Exception as e:
        print(f"Erro ao buscar LoL: {e}")
    
    return campeonatos

def buscar_campeonatos_hltv() -> List[Dict]:
    """Busca campeonatos de CS:GO/CS2 do HLTV"""
    url = 'https://www.hltv.org/events'
    campeonatos = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        
        for item in soup.select('.event-item')[:15]:  # Limita a 15
            try:
                link_elem = item.select_one('a')
                link = link_elem.get('href', '') if link_elem else ''
                if link and link.startswith('/'):
                    link = 'https://www.hltv.org' + link
                
                nome_elem = item.select_one('.event-item-title')
                nome = nome_elem.get_text(strip=True) if nome_elem else ''
                
                data_elem = item.select_one('.event-item-date')
                data = data_elem.get_text(strip=True) if data_elem else ''
                
                if nome and link:
                    evento = extrair_campeonato('CS2', nome, data, link, link)
                    campeonatos.append(evento)
            except Exception:
                continue
    except Exception as e:
        print(f"Erro ao buscar HLTV: {e}")
    
    return campeonatos

def salvar_cache(campeonatos: List[Dict]) -> None:
    """Salva campeonatos em cache"""
    try:
        dados = {
            'timestamp': datetime.now().isoformat(),
            'campeonatos': campeonatos
        }
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar cache: {e}")


def carregar_cache() -> Optional[List[Dict]]:
    """Carrega campeonatos do cache se for do mesmo dia"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                data_cache = datetime.fromisoformat(dados['timestamp'])
                if data_cache.date() == datetime.now().date():
                    return dados['campeonatos']
    except Exception as e:
        print(f"Erro ao carregar cache: {e}")
    return None


def buscar_todos_campeonatos(force_update: bool = False) -> List[Dict]:
    """Busca todos os campeonatos (LoL, CS2, Valorant) ou retorna do cache"""
    if not force_update:
        cache = carregar_cache()
        if cache:
            return cache
    
    campeonatos = []
    
    # Busca de cada fonte
    print("Buscando campeonatos...")
    campeonatos.extend(buscar_campeonatos_vlr())
    campeonatos.extend(buscar_campeonatos_lol())
    campeonatos.extend(buscar_campeonatos_hltv())
    
    # Se nada foi encontrado, retorna seed
    if not campeonatos:
        campeonatos = campeonatos_seed()
    
    # Remove duplicatas por slug
    vistos = set()
    unicos = []
    for c in campeonatos:
        if c['slug'] not in vistos:
            vistos.add(c['slug'])
            unicos.append(c)
    
    salvar_cache(unicos)
    return unicos


def campeonatos_seed() -> List[Dict]:
    """Seed de exemplo para testes (quando nenhuma fonte retorna dados)"""
    now = datetime.now().isoformat()
    return [
        extrair_campeonato('League of Legends', 'CBLOL - Fase Final',  
                          now, 'https://lolesports.com', 'https://lolesports.com'),
        extrair_campeonato('Valorant', 'VCT 2025',
                          now, 'https://vlr.gg/events', 'https://vlr.gg/events'),
        extrair_campeonato('CS2', 'PGL Major',
                          now, 'https://hltv.org/events', 'https://hltv.org/events'),
    ]


if __name__ == '__main__':
    # Teste rápido
    campeonatos = buscar_todos_campeonatos(force_update=True)
    print(f"\nEncontrados {len(campeonatos)} campeonatos:")
    for c in campeonatos[:5]:
        print(f"  - {c['jogo']}: {c['nome']} ({c.get('slug', 'sem-slug')})")