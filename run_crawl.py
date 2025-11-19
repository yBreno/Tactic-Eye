from app_v2 import processar_feed, FEEDS_RSS
from database import save_noticia

if __name__ == '__main__':
    print('Iniciando crawl de teste...')
    noticias = processar_feed(FEEDS_RSS[0], max_noticias=5)
    print('Encontradas:', len(noticias))
    for n in noticias:
        ok = save_noticia(n)
        print('Salvou:', ok, n.get('link'))
    print('Concluído')
