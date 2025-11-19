import os
import time
import hashlib
import concurrent.futures
from urllib.parse import urljoin, urlparse, quote_plus
from flask import Flask, jsonify, request, render_template, redirect, url_for

# banco de dados
from database import init_db, save_noticia, get_noticias, get_noticia_by_url

import feedparser
import requests
from bs4 import BeautifulSoup
import threading
import uuid
import sqlite3
from datetime import datetime
from threading import Lock
from campeonatos import buscar_todos_campeonatos
from filtros import eh_noticia_relevante
import re

app = Flask(__name__)

# ======================== CONFIGURAÇÃO ========================
USUARIO_AGENTE = 'RastreadorNoticias/1.0 (+https://example.com)'
CABECALHOS = {'User-Agent': USUARIO_AGENTE}
TEMPO_LIMITE_REQUISICAO = 10
INTERVALO_ENTRE_REQUISICOES = 2.0
DIRETORIO_SAIDA = 'saida'
DIRETORIO_IMAGENS = os.path.join(DIRETORIO_SAIDA, 'imagens')

FEEDS_RSS = [
    # Feeds de Tecnologia
    'https://g1.globo.com/rss/g1/tecnologia/',          # Tecnologia G1
    'https://feeds.feedburner.com/tecmundo',            # TecMundo
    'https://tecnoblog.net/feed/',                      # Tecnoblog
    # Feeds de Jogos e eSports
    'https://www.theenemy.com.br/feed',                 # The Enemy (Games)
    'https://www.espn.com.br/esports/rss.xml',         # ESPN eSports
    'https://www.dexerto.com/feed/',                    # Dexerto (eSports)
    'https://www.vlr.gg/rss',                          # VLR.gg (VALORANT)
    'https://www.hltv.org/rss/news',                   # HLTV (CS:GO)
]

def garantir_diretorios():
    os.makedirs(DIRETORIO_SAIDA, exist_ok=True)
    os.makedirs(DIRETORIO_IMAGENS, exist_ok=True)
    os.makedirs('.cache/html', exist_ok=True)

# HTML cache config (24h)
CACHE_HTML_DIR = os.path.join('.cache', 'html')
CACHE_HTML_TTL = 24 * 60 * 60

# Campeonatos cache (1h)
CAMPEONATOS_CACHE = {'data': None, 'ts': 0}
CAMPEONATOS_TTL = 60 * 60

def limpar_html_resumo(html_resumo: str) -> str:
    """Remove imagens, scripts e retorna apenas texto limpo."""
    if not html_resumo:
        return ""

    soup = BeautifulSoup(html_resumo, "html.parser")

    # Remove <img>, <script>, <style>, <iframe>
    for tag in soup.find_all(["img", "script", "style", "iframe"]):
        tag.decompose()

    # Retorna só texto limpo
    return soup.get_text(" ", strip=True)

def get_cached_campeonatos(force_update: bool = False):
    now = int(time.time())
    if not force_update and CAMPEONATOS_CACHE['data'] and (now - CAMPEONATOS_CACHE['ts'] < CAMPEONATOS_TTL):
        return CAMPEONATOS_CACHE['data']
    try:
        data = buscar_todos_campeonatos(force_update=force_update)
        CAMPEONATOS_CACHE['data'] = data
        CAMPEONATOS_CACHE['ts'] = now
        return data
    except Exception as e:
        print(f"Erro ao buscar campeonatos (cache): {e}")
        return CAMPEONATOS_CACHE['data'] or []


def schedule_image_download(url_imagem: str):
    """Inicia download de imagem em background (não bloqueante)."""
    if not url_imagem:
        return

    def _job(u):
        try:
            caminho = baixar_imagem(u)
            if caminho:
                print(f"Imagem baixada em background: {caminho}")
        except Exception as e:
            print(f"Erro no download de imagem em background: {e}")

    t = threading.Thread(target=_job, args=(url_imagem,), daemon=True)
    t.start()



def gerar_slug(texto: str) -> str:
    texto_limpo = ''.join(c if c.isalnum() else '_' for c in texto).strip('_')
    if len(texto_limpo) == 0:
        texto_limpo = hashlib.md5(texto.encode('utf-8')).hexdigest()[:8]
    return texto_limpo[:120]

def buscar_url(url: str, max_tentativas: int = 2, timeout: int = 6):
    """Busca uma URL com um número reduzido de tentativas e timeout configurável.

    Reduz o timeout padrão para evitar travamento em feeds grandes.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    for tentativa in range(max_tentativas):
        try:
            print(f"Tentativa {tentativa + 1} para URL: {url}")
            resposta = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            resposta.raise_for_status()
            print(f"URL {url} acessada com sucesso!")
            return resposta
        except Exception as erro:
            print(f"Tentativa {tentativa + 1} falhou para URL {url}: {erro}")
            if tentativa < max_tentativas - 1:
                time.sleep(1.5 * (tentativa + 1))  # Espera progressiva mais curta
                continue
    print(f"Todas as {max_tentativas} tentativas falharam para URL {url}")
    return None

def analisar_artigo(url: str, html_texto: str):
    """Analisa o artigo usando BeautifulSoup."""
    sopa = BeautifulSoup(html_texto, 'lxml')

    # Extrai o título
    titulo_tag = sopa.find('meta', property='og:title') or sopa.find('title')
    if titulo_tag and titulo_tag.has_attr('content'):
        titulo = titulo_tag.get('content')
    else:
        titulo = titulo_tag.get_text(strip=True) if titulo_tag else ''

    # Extrai a descrição/resumo
    descricao_tag = sopa.find('meta', property='og:description') or sopa.find('meta', attrs={'name': 'description'})
    descricao = descricao_tag.get('content') if descricao_tag and descricao_tag.has_attr('content') else None

    # Extrai o texto principal de forma mais robusta
    texto = ''
    # 1) tenta encontrar tag <article>
    article = sopa.find('article')
    if article:
        texto = article.get_text(separator='\n\n').strip()
    else:
        # 2) tenta contêineres com id/class comuns
        main_container = sopa.find(attrs={'id': re.compile('(content|main|article|post)', re.I)})
        if not main_container:
            main_container = sopa.find('div', class_=re.compile('(content|article|post|main|entry)', re.I))
        if main_container:
            texto = main_container.get_text(separator='\n\n').strip()
        else:
            # 3) fallback: junta todos os <p>
            paragrafos = [p.get_text(strip=True) for p in sopa.find_all('p') if p.get_text(strip=True)]
            texto = '\n\n'.join(paragrafos)

    # Extrai imagens
    imagens = []
    og_imagem = sopa.find('meta', property='og:image')
    if og_imagem and og_imagem.get('content'):
        imagens.append(urljoin(url, og_imagem.get('content')))

    for img in sopa.find_all('img', src=True):
        src = img['src']
        completo = urljoin(url, src)
        if completo not in imagens:
            imagens.append(completo)
        if len(imagens) >= 5:
            break

    return {
        'url': url,
        'titulo': titulo.strip() if titulo else '',
        'resumo': descricao,
        'texto': texto.strip(),
        'imagem_principal': imagens[0] if imagens else None,
        'imagens': imagens,
    }


def _cache_path_for_url(url: str, prefix: str = 'html') -> str:
    nome = hashlib.md5(url.encode('utf-8')).hexdigest()
    if prefix == 'html':
        return os.path.join(CACHE_HTML_DIR, f"{nome}.html")
    return os.path.join('.cache', f"{prefix}-{nome}")


def fetch_with_cache(url: str, ttl: int = CACHE_HTML_TTL) -> str | None:
    """Busca o HTML de uma URL usando cache local com TTL em segundos."""
    caminho = _cache_path_for_url(url, 'html')
    try:
        if os.path.exists(caminho):
            mtime = int(os.path.getmtime(caminho))
            if int(time.time()) - mtime < ttl:
                try:
                    with open(caminho, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    pass

        resp = buscar_url(url, max_tentativas=2, timeout=6)
        if resp and resp.text:
            try:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(resp.text)
            except Exception:
                pass
            return resp.text
    except Exception as e:
        print(f"Erro ao buscar/cachear URL {url}: {e}")
    return None

def baixar_imagem(url_imagem: str):
    try:
        resposta = requests.get(url_imagem, headers=CABECALHOS, timeout=TEMPO_LIMITE_REQUISICAO)
        resposta.raise_for_status()
        extensao = os.path.splitext(urlparse(url_imagem).path)[1].split('?')[0]
        if not extensao or len(extensao) > 6:
            extensao = '.jpg'
        nome_arquivo = gerar_slug(url_imagem) + extensao
        caminho = os.path.join(DIRETORIO_IMAGENS, nome_arquivo)
        with open(caminho, 'wb') as arquivo:
            arquivo.write(resposta.content)
        return caminho
    except Exception as erro:
        print(f"Falha ao baixar imagem {url_imagem}: {erro}")
        return None

def processar_feed(url_feed: str, max_noticias=10):
    print(f"\nProcessando feed: {url_feed}")
    resultados = []
    timestamp_atual = int(time.time())
    
    try:
        # Baixa o feed com requests para garantir User-Agent correto
        try:
            resp = requests.get(url_feed, headers={'User-Agent': CABECALHOS['User-Agent']}, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e_fetch:
            print(f"Falha ao baixar feed com requests ({e_fetch}), tentando feedparser direto...")
            feed = feedparser.parse(url_feed)

        print(f"Status do feed: {feed.get('status', 'N/A')}")
        print(f"Número de entradas: {len(feed.entries) if hasattr(feed, 'entries') else 0}")
        
        if hasattr(feed, 'bozo_exception') and feed.bozo_exception:
            print(f"Erro ao analisar feed {url_feed}: {feed.bozo_exception}")
            return []
        if hasattr(feed, 'status') and isinstance(feed.status, int) and feed.status >= 400:
            print(f"Erro ao acessar feed {url_feed}: HTTP {feed.status}")
            return []
        if not feed.entries:
            print(f"Feed {url_feed} não contém entradas")
            return []
    except Exception as e:
        print(f"Erro ao processar feed {url_feed}: {e}")
        return []
    
    print(f"Feed {url_feed} contém {len(feed.entries)} entradas")
    entries_to_process = feed.entries[:max_noticias]

    for i, entrada in enumerate(entries_to_process, 1):
        try:
            print(f"\nNotícia {i} de {len(entries_to_process)}: {entrada.get('title', 'Sem título')}")

            # tenta obter link em vários campos
            link_entry = entrada.get('link') or (entrada.links[0].href if ('links' in entrada and entrada.links) else None) or entrada.get('id')
            if not link_entry:
                print("Notícia sem link, pulando...")
                continue

            # Processa a data de publicação (se disponível)
            data_publicacao = entrada.get('published_parsed') or entrada.get('updated_parsed')
            if data_publicacao:
                timestamp_publicacao = int(time.mktime(data_publicacao))
            else:
                timestamp_publicacao = timestamp_atual

            resumo_feed_sujo = entrada.get('summary') if 'summary' in entrada else (
    entrada.get('description') if 'description' in entrada else ''
)

# LIMPA o HTML sujo vindo do feed
            resumo_feed = limpar_html_resumo(resumo_feed_sujo)

            titulo_feed = entrada.get('title') or ''
            titulo_feed = entrada.get('title') or ''

            # Filtra por relevância usando título/resumo do feed antes de baixar HTML
            if not eh_noticia_relevante(titulo=titulo_feed, texto='', resumo=resumo_feed or ''):
                print('Descartada por relevância (base no feed)')
                continue

            # Monta notícia mínima a partir do feed
            noticia = {
                'feed': url_feed,
                'titulo': titulo_feed,
                'link': link_entry,
                'publicado': entrada.get('published') or entrada.get('updated') or '',
                'resumo': resumo_feed,
                'added_at': timestamp_publicacao
            }

            # Busca HTML com cache (só para notícias relevantes)
            html = fetch_with_cache(link_entry)
            if html:
                artigo = analisar_artigo(link_entry, html)
                # Não baixar imagem aqui (evita bloqueio); só salvar URL
                noticia.update({
                    'texto': artigo.get('texto', ''),
                    'imagem_principal': artigo.get('imagem_principal')
                })

            resultados.append(noticia)
            print('Notícia relevante processada (feed + análise).')
        except Exception as e:
            print(f"Erro ao processar notícia: {e}")
            continue

    return resultados


from database import init_db, save_noticia, get_noticias, get_noticia_by_url

def load_archive():
    """Carrega notícias do banco de dados"""
    try:
        resultado = get_noticias(page=1, per_page=1000)  # Carrega um lote grande
        return resultado['noticias']
    except Exception as e:
        print(f'Erro ao carregar notícias do banco: {e}')
        return []

def save_archive(items):
    """Salva notícias no banco de dados"""
    try:
        for item in items:
            save_noticia(item)
    except Exception as e:
        print(f'Erro ao salvar notícias no banco: {e}')


# -------------------- Job manager (background crawl) --------------------
JOBS = {}
JOBS_LOCK = Lock()

def _create_job_entry(feeds, max_noticias):
    job_id = str(uuid.uuid4())
    entry = {
        'id': job_id,
        'status': 'pending',  # pending, running, done, failed
        'created_at': int(time.time()),
        'started_at': None,
        'finished_at': None,
        'feeds': feeds,
        'max_noticias': max_noticias,
        'total_found': 0,
        'error': None,
        'log': []
    }
    with JOBS_LOCK:
        JOBS[job_id] = entry
    return job_id

def _update_job(job_id, **kwargs):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(kwargs)

def run_crawl_job(job_id, feeds, max_noticias):
    """Função que executa o crawl (pode rodar em thread)."""
    try:
        _update_job(job_id, status='running', started_at=int(time.time()))
        todas_noticias = []
        # Processa feeds em paralelo com pool limitado para evitar muitas threads
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as exc:
                future_to_feed = {exc.submit(processar_feed, feed, max_noticias): feed for feed in feeds}
                for fut in concurrent.futures.as_completed(future_to_feed):
                    feed = future_to_feed[fut]
                    try:
                        noticias = fut.result()
                        todas_noticias.extend(noticias)
                        _update_job(job_id, log=JOBS[job_id]['log'] + [f"Encontradas {len(noticias)} noticias no feed {feed}"])
                    except Exception as erro:
                        _update_job(job_id, log=JOBS[job_id]['log'] + [f"Erro ao processar feed {feed}: {erro}"])
        except Exception as e:
            print(f"Erro no pool de threads ao processar feeds: {e}")
        arquivo_existente = load_archive()
        novo_arquivo = merge_archives(arquivo_existente, todas_noticias)
        save_archive(novo_arquivo)
        _update_job(job_id, status='done', finished_at=int(time.time()), total_found=len(todas_noticias))
    except Exception as e:
        _update_job(job_id, status='failed', error=str(e), finished_at=int(time.time()))



def merge_archives(existing, novas):
    """Salva as novas notícias no banco e retorna a lista atualizada."""
    try:
        # Forçar atualização para garantir novas notícias
        print(f"Mesclando {len(novas)} notícias novas...")
        
        # Garante que todas as notícias novas tenham timestamp atual
        timestamp_atual = int(time.time())
        
        # Limpa cache existente para forçar atualização
        conn = sqlite3.connect('noticias.db')
        cursor = conn.cursor()
        try:
            # Remove notícias antigas (mais de 7 dias)
            sete_dias = timestamp_atual - (7 * 24 * 60 * 60)
            cursor.execute('DELETE FROM noticias WHERE added_at < ?', (sete_dias,))
            conn.commit()
        except Exception as e:
            print(f"Erro ao limpar cache: {e}")
        finally:
            conn.close()
            
        # Atualiza timestamp para todas as notícias novas
        for noticia in novas:
            noticia['added_at'] = timestamp_atual  # Força timestamp atual para todas
        
        # carregar campeonatos (cacheado) para tentar associar cada notícia
        campeonatos = get_cached_campeonatos(force_update=False) or []

        for noticia in novas:
            # garantir tipo e campos mínimos
            if not isinstance(noticia, dict):
                continue
            if not noticia.get('link'):
                continue

            # evita duplicação: se notícia já existe com added_at igual/mais recente, pula
            try:
                existente = get_noticia_by_url(noticia.get('link'))
                if existente:
                    try:
                        existente_ts = int(existente.get('added_at') or 0)
                    except Exception:
                        existente_ts = 0
                    nova_ts = int(noticia.get('added_at') or time.time())
                    if existente_ts >= nova_ts:
                        # já existe notícia igual ou mais nova
                        print(f"Pulando notícia duplicada/antiga: {noticia.get('link')}")
                        continue
            except Exception as e:
                print(f"Erro ao checar duplicados no DB: {e}")

            if not noticia.get('added_at'):
                noticia['added_at'] = int(time.time())

            # tentar associar a um campeonato pelo título/resumo (matching simples)
            try:
                titulo = (noticia.get('titulo') or '').lower()
                resumo = (noticia.get('resumo') or '').lower()
                noticia['campeonato_slug'] = ''
                for c in campeonatos:
                    nome_c = (c.get('nome') or '').lower()
                    jogo_c = (c.get('jogo') or '').lower()
                    # match simples: nome do campeonato aparecendo no título ou resumo
                    if nome_c and len(nome_c) > 3 and (nome_c in titulo or nome_c in resumo):
                        noticia['campeonato_slug'] = c.get('slug') or ''
                        noticia['campeonato_nome'] = c.get('nome')
                        break
                    # ou jogo associado (ex: 'valorant', 'league of legends')
                    if jogo_c and jogo_c in titulo and not noticia['campeonato_slug']:
                        noticia['campeonato_slug'] = c.get('slug') or ''
                        noticia['campeonato_nome'] = c.get('nome')
                        break
            except Exception as e:
                print(f"Erro ao tentar associar campeonato: {e}")

            # salva no banco (save_noticia já trata defaults)
            saved = False
            try:
                saved = save_noticia(noticia)
            except Exception as e:
                print(f"Erro ao salvar notícia: {e}")

            # se houver imagem remota, agendar download em background (não bloqueante)
            try:
                if noticia.get('imagem_principal'):
                    schedule_image_download(noticia.get('imagem_principal'))
            except Exception as e:
                print(f"Erro ao agendar download de imagem: {e}")

        # retorna a listagem atualizada (página 1)
        resultado = get_noticias(page=1, per_page=1000)
        return resultado['noticias']
    except Exception as e:
        print(f"Erro ao mesclar notícias: {e}")
        return existing


def rewrite_with_openai(texto: str, api_key: str, model: str = 'gpt-3.5-turbo') -> str:
    """Usa a API do OpenAI para reescrever o texto em português.
    Retorna o texto reescrito ou lança Exception em caso de erro."""
    if not api_key:
        raise ValueError('API key do OpenAI não fornecida')

    url = 'https://api.openai.com/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    prompt = (
        "Você é um assistente que reescreve textos em português com um tom mais jovem, dinâmico e voltado para o público gamer, "
        "Mantenha o sentido da mensagem, mas deixe a escrita mais leve, natural e com linguagem do dia a dia, sem copiar partes do texto original e sem mencionar quem escreveu.\n\n"
        f"Texto original:\n{texto}\n\nReescreva-o:" 
    )

    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'Você reescreve textos em Português mantendo sentido e evitando plágio.'},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.7,
        'max_tokens': 1500,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Extrai o conteúdo da resposta
    try:
        texto_reescrito = data['choices'][0]['message']['content'].strip()
    except Exception as e:
        raise RuntimeError(f'Resposta inesperada da API: {e}')

    return texto_reescrito


def simple_rewrite(texto: str) -> str:
    """Fallback simples que faz pequenas transformações locais quando não há API disponível.
    Não substitui uma IA real, mas serve como demonstrativo."""
    # Estratégia simples: dividir em sentenças, evitar repetições e reescrever frases curtas
    import re
    frases = [s.strip() for s in re.split(r'(?<=[.!?])\s+', texto) if s.strip()]
    out = []
    subs = {
        'porém': 'contudo',
        'mas': 'porém',
        'além disso': 'além disso',
        'dessa forma': 'assim',
        'muito': 'bastante'
    }
    for f in frases:
        nova = f
        for k, v in subs.items():
            nova = nova.replace(k, v)
        out.append(nova)
    # retorna juntando com espaçamento, adicionando aviso que é reescrita simples
    return ' '.join(out)


@app.route('/api/rewrite', methods=['POST'])
def api_rewrite():
    """
    Reescreve o texto da notícia apontada por uma URL usando IA.
    POST /api/rewrite
    {
        "url": "https://...",
        "provider": "openai",         # opcional, default openai
        "api_key": "...",            # opcional. se não informado, tenta usar OPENAI_API_KEY env
        "model": "gpt-3.5-turbo"     # opcional
    }
    """
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({'sucesso': False, 'erro': 'Campo "url" é obrigatório.'}), 400

    provider = data.get('provider', 'openai')
    api_key = data.get('api_key') or os.environ.get('OPENAI_API_KEY')
    model = data.get('model', 'gpt-3.5-turbo')

    resposta = buscar_url(url)
    if not resposta:
        return jsonify({'sucesso': False, 'erro': 'Falha ao acessar a URL'}), 400

    artigo = analisar_artigo(url, resposta.text)
    texto_original = artigo.get('texto') or artigo.get('resumo') or ''
    if not texto_original:
        return jsonify({'sucesso': False, 'erro': 'Não foi possível extrair o texto da notícia.'}), 400

    try:
        if provider == 'openai' and api_key:
            texto_reescrito = rewrite_with_openai(texto_original, api_key, model=model)
        else:
            # fallback local
            texto_reescrito = simple_rewrite(texto_original)
    except Exception as erro:
        # caso OpenAI falhe, tentar fallback simples
        print(f'Erro ao usar provider {provider}: {erro}')
        texto_reescrito = simple_rewrite(texto_original)

    resultado = {
        'sucesso': True,
        'url': url,
        'titulo': artigo.get('titulo'),
        'texto_original': texto_original,
        'texto_reescrito': texto_reescrito
    }

    return jsonify(resultado)

# ======================== ROTAS DA API ========================

@app.route('/')
def index():
    """
    Página inicial com links para a documentação da API
    """
    try:
        # Tentar carregar destaques do arquivo histórico (mais notícias antigas)
        destaques = []
        arqu = load_archive()
        if arqu:
            for n in arqu[:6]:
                resumo = n.get('resumo') or (n.get('texto')[:300] + '...') if n.get('texto') else ''
                n['resumo_curto'] = resumo
                n['link_encoded'] = quote_plus(n.get('link', ''))
                destaques.append(n)
        else:
            # fallback: buscar feeds ao vivo para preencher destaques
            for feed in FEEDS_RSS:
                noticias = processar_feed(feed, max_noticias=3)
                for n in noticias:
                    resumo = n.get('resumo') or (n.get('texto')[:300] + '...') if n.get('texto') else ''
                    n['resumo_curto'] = resumo
                    n['link_encoded'] = quote_plus(n.get('link', ''))
                    destaques.append(n)
                    if len(destaques) >= 6:
                        break
                if len(destaques) >= 6:
                    break

        return render_template('base.html', pagina='index', destaques=destaques)
    except Exception as e:
        return render_template('base.html', pagina='erro', erro=str(e))

@app.route('/noticias')
def noticias():
    """
    Página que mostra as últimas notícias já reescritas
    """
    try:
        # Força página 1 se estiver atualizando
        is_updating = request.args.get('updating') == '1'
        if is_updating:
            page = 1
        else:
            try:
                page = int(request.args.get('page', '1'))
                if page < 1:
                    page = 1
            except ValueError:
                page = 1
        
        # Busca direto do banco de dados com paginação
        resultado = get_noticias(page=page, per_page=10)
        print(f"Encontradas {len(resultado['noticias'])} notícias na página {page}")
        
        if not resultado['noticias']:
            # Se não houver notícias, buscar apenas do primeiro feed para carregar rápido
            print("Buscando notícias iniciais...")
            noticias_feed = processar_feed(FEEDS_RSS[0], max_noticias=5)
            
            if noticias_feed:
                save_archive(noticias_feed)
                # Busca novamente do banco após salvar
                resultado = get_noticias(page=page, per_page=10)
                
                # Inicia uma thread para buscar o resto das notícias em background
                def buscar_resto_background():
                    # Processa os feeds restantes com um pool pequeno
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
                            futures = [ex.submit(processar_feed, f, 5) for f in FEEDS_RSS[1:]]
                            for fut in concurrent.futures.as_completed(futures):
                                try:
                                    mais_noticias = fut.result()
                                    save_archive(mais_noticias)
                                except Exception as e:
                                    print(f"Erro ao buscar feed em background: {e}")
                    except Exception as e:
                        print(f"Erro no background pool: {e}")
                
                thread = threading.Thread(target=buscar_resto_background, daemon=True)
                thread.start()
            else:
                return render_template('base.html', pagina='noticias', noticias=[], 
                                    meta={'page': 1, 'pages': 1, 'total': 0},
                                    mensagem="Nenhuma notícia disponível no momento.")

        # Garantir resumo e link codificado para cada notícia exibida
        for noticia in resultado['noticias']:
            if not noticia.get('resumo'):
                noticia['resumo'] = (noticia.get('texto') or '')[:400]
            noticia['link_encoded'] = quote_plus(noticia.get('link', ''))

        return render_template('base.html', pagina='noticias', 
                             noticias=resultado['noticias'], 
                             meta={
                                 'page': page,
                                 'pages': resultado['pages'],
                                 'total': resultado['total']
                             })
    except Exception as erro:
        print(f"Erro na rota /noticias: {erro}")
        return render_template('base.html', pagina='erro', erro=str(erro))


@app.route('/ver')
def ver_noticia():
    """Renderiza a notícia completa (conteúdo extraído) a partir da URL codificada em query param 'url'."""
    url = request.args.get('url')
    if not url:
        return render_template('base.html', pagina='erro', erro='Parâmetro url ausente')
    # url pode vir codificada
    from urllib.parse import unquote_plus
    url = unquote_plus(url)
    # tenta obter HTML do cache antes de baixar
    html = fetch_with_cache(url)
    if not html:
        resposta = buscar_url(url)
        if not resposta:
            return render_template('base.html', pagina='erro', erro='Falha ao buscar a notícia')
        html = resposta.text

    artigo = analisar_artigo(url, html)
    # baixar imagem local se existir
    if artigo and artigo.get('imagem_principal'):
        caminho = baixar_imagem(artigo['imagem_principal'])
        if caminho:
            artigo['imagem_principal_local'] = caminho

    return render_template('base.html', pagina='ver', artigo=artigo)


@app.route('/campeonatos')
def campeonatos():
    """
    Página que mostra os campeonatos de eSports
    """
    try:
        # Usa cache quando possível; botão de atualização pode forçar update
        campeonatos = get_cached_campeonatos(force_update=False)
        return render_template('campeonatos.html', campeonatos=campeonatos)
    except Exception as e:
        print(f"Erro na rota /campeonatos: {e}")
        return render_template('base.html', pagina='erro', erro=str(e))


@app.route('/campeonatos/event/<slug>')
def campeonato_event(slug):
    """Página de detalhe para um campeonato (dados servidos localmente)."""
    try:
        campeonatos = get_cached_campeonatos(force_update=False)
        for c in campeonatos:
            if c.get('slug') == slug:
                # garantir campos mínimos
                if not c.get('teams') and c.get('times'):
                    c['teams'] = c.get('times')
                return render_template('campeonato_detalhe.html', campeonato=c)
        return render_template('base.html', pagina='erro', erro='Campeonato não encontrado'), 404
    except Exception as e:
        print(f"Erro na rota /campeonatos/event/{slug}: {e}")
        return render_template('base.html', pagina='erro', erro=str(e))


@app.route('/campeonatos/<slug>/noticias')
def noticias_por_campeonato(slug):
    """Lista notícias associadas a um campeonato (consulta rápida via DB)."""
    try:
        # paginação simples via ?page=N
        try:
            page = int(request.args.get('page', '1'))
            if page < 1:
                page = 1
        except ValueError:
            page = 1

        # buscar notícias filtradas pelo slug
        from database import get_noticias_por_campeonato
        resultado = get_noticias_por_campeonato(slug, page=page, per_page=10)

        # garantir resumo e link codificado
        noticias = resultado.get('noticias', [])
        for noticia in noticias:
            if not noticia.get('resumo'):
                noticia['resumo'] = (noticia.get('texto') or '')[:400]
            noticia['link_encoded'] = quote_plus(noticia.get('link', ''))

        # buscar dados do campeonato para mostrar título/descrição
        campeonatos = get_cached_campeonatos(force_update=False)
        campeonato = None
        for c in campeonatos:
            if c.get('slug') == slug:
                campeonato = c
                break

        return render_template('base.html', pagina='noticias', noticias=noticias,
                               meta={'page': page, 'pages': resultado.get('pages', 1), 'total': resultado.get('total', 0)},
                               campeonato=campeonato)
    except Exception as e:
        print(f"Erro na rota /campeonatos/{slug}/noticias: {e}")
        return render_template('base.html', pagina='erro', erro=str(e))

@app.route('/api/crawl', methods=['POST'])
def api_crawl():
    """
    Endpoint para iniciar o rastreamento de feeds.
    Aceita tanto JSON quanto form-data:
    POST /api/crawl
    {
        "feeds": ["url1", "url2", ...],  // opcional, usa FEEDS_RSS por padrão
        "max_noticias": 10               // opcional, padrão é 10
    }
    """
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = request.form.to_dict()
    
    feeds = data.get('feeds', FEEDS_RSS)
    if isinstance(feeds, str):
        # Se vier como string (do form), usar todos os feeds
        feeds = FEEDS_RSS
    max_noticias = int(data.get('max_noticias', 10))
    
    # Se a requisição veio do formulário, sempre executar em background
    is_form = not request.is_json
    background = True if is_form else bool(data.get('background', False))

    if background:
        # criar job e iniciar thread
        job_id = _create_job_entry(feeds, max_noticias)
        thread = threading.Thread(target=run_crawl_job, args=(job_id, feeds, max_noticias), daemon=True)
        thread.start()
        return jsonify({'sucesso': True, 'background': True, 'job_id': job_id}), 202

    # comportamento síncrono (como antes)
    todas_noticias = []
    for feed in feeds:
        try:
            noticias = processar_feed(feed, max_noticias)
            # Adiciona timestamp atual para garantir ordem correta
            for noticia in noticias:
                noticia['added_at'] = int(time.time())
            todas_noticias.extend(noticias)
            print(f"Encontradas {len(noticias)} novas notícias em {feed}")
        except Exception as erro:
            print(f"Erro ao processar o feed {feed}: {erro}")

    print(f"Total de {len(todas_noticias)} novas notícias encontradas")
    
    # carregar arquivo existente e mesclar
    arquivo_existente = load_archive()
    novo_arquivo = merge_archives(arquivo_existente, todas_noticias)
    save_archive(novo_arquivo)

    if is_form:
        # Redirecionar de volta para a página de notícias
        return redirect(url_for('noticias'))
    else:
        # Retornar JSON para chamadas da API
        return jsonify({
            'sucesso': True,
            'total_noticias': len(todas_noticias),
            'noticias': todas_noticias
        })


@app.route('/api/crawl/status/<job_id>', methods=['GET'])
def api_crawl_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({'sucesso': False, 'erro': 'Job não encontrado'}), 404
    # retornar campos públicos
    public = {
        'id': job['id'],
        'status': job['status'],
        'created_at': job['created_at'],
        'started_at': job.get('started_at'),
        'finished_at': job.get('finished_at'),
        'feeds': job.get('feeds'),
        'max_noticias': job.get('max_noticias'),
        'total_found': job.get('total_found'),
        'error': job.get('error'),
        'log': job.get('log', [])
    }
    return jsonify({'sucesso': True, 'job': public})

@app.route('/api/feeds', methods=['GET'])
def api_feeds():
    """
    Retorna a lista de feeds RSS configurados
    GET /api/feeds
    """
    return jsonify({
        'feeds': FEEDS_RSS
    })

@app.route('/api/noticia', methods=['POST'])
def api_noticia():
    """
    Analisa uma URL específica
    POST /api/noticia
    {
        "url": "url_da_noticia"
    }
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({
            'sucesso': False,
            'erro': 'URL não fornecida'
        }), 400
    
    url = data['url']
    resposta = buscar_url(url)
    
    if not resposta:
        return jsonify({
            'sucesso': False,
            'erro': 'Falha ao acessar a URL'
        }), 400
    
    artigo = analisar_artigo(url, resposta.text)
    
    if artigo and artigo.get('imagem_principal'):
        caminho_imagem = baixar_imagem(artigo['imagem_principal'])
        if caminho_imagem:
            artigo['imagem_principal_local'] = caminho_imagem
    
    return jsonify({
        'sucesso': True,
        'artigo': artigo
    })

if __name__ == '__main__':
    garantir_diretorios()
    # Inicializa o banco de dados
    init_db()
    print("Servidor iniciando... Acesse http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)