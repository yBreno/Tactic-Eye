import sys
from app_v2 import processar_feed, FEEDS_RSS, garantir_diretorios
from database import save_noticia, init_db
import time

# Evita UnicodeEncodeError na saída do Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    # Python <3.7 ou ambientes onde reconfigure não existe podem falhar — ignorar
    pass

if __name__ == '__main__':
    garantir_diretorios()
    init_db()
    total_saved = 0
    total_found = 0
    per_feed = 30
    start = time.time()
    print('Iniciando crawl completo: %d feeds, %d notícias por feed (máx)' % (len(FEEDS_RSS), per_feed))
    for feed in FEEDS_RSS:
        print('\n--- Processando feed:', feed)
        noticias = processar_feed(feed, max_noticias=per_feed)
        found = len(noticias)
        saved = 0
        print('Encontradas %d entradas no feed %s' % (found, feed))
        for n in noticias:
            try:
                ok = save_noticia(n)
                if ok:
                    saved += 1
            except Exception as e:
                print('Erro ao salvar noticia:', e)
        print('Salvas %d/%d do feed' % (saved, found))
        total_saved += saved
        total_found += found
        # pequeno atraso para evitar bursts
        time.sleep(1)
    elapsed = time.time() - start
    print('\nCrawl completo. Encontradas:', total_found, 'Salvas:', total_saved, 'Tempo(s): %.1f' % elapsed)
