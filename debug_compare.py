import feedparser
import json
from database import get_noticias
from urllib.parse import urlparse

FEED = 'https://g1.globo.com/rss/g1/tecnologia/'

print('Baixando feed:', FEED)
feed = feedparser.parse(FEED)
print('Status:', getattr(feed, 'status', 'N/A'))
print('Entradas no feed:', len(feed.entries))

feed_links = []
for e in feed.entries[:50]:
    link = e.get('link') or (e.links[0].href if (hasattr(e, 'links') and e.links) else e.get('id'))
    title = e.get('title')
    feed_links.append({'link': link, 'title': title})

print('\nPrimeiras entradas do feed:')
for i, l in enumerate(feed_links[:10], 1):
    print(i, l['link'], '-', l.get('title'))

res = get_noticias(page=1, per_page=1000)
db_links = [n['link'] for n in res['noticias']]
print('\nTotal no DB:', res['total'])

print('\nLinks no DB (primeiros 20):')
for i, l in enumerate(db_links[:20], 1):
    print(i, l)

missing = [f for f in feed_links if f['link'] not in db_links]
print('\nLinks do feed que NAO estao no DB (primeiros 50):')
for i, m in enumerate(missing[:50], 1):
    print(i, m['link'], '-', m.get('title'))

print('\nTotal missing from feed:', len(missing))

# Also print example of DB links that are similar (normalized)

def normalize(u):
    if not u:
        return ''
    p = urlparse(u)
    # remove query params and fragment
    return p.scheme + '://' + p.netloc + p.path.rstrip('/')

norm_db = {normalize(u): u for u in db_links}

similar = []
for f in feed_links:
    n = normalize(f['link'])
    if n in norm_db and norm_db[n] != f['link']:
        similar.append((f['link'], norm_db[n]))

print('\nExemplos de URLs similares entre feed e DB (normalizado):')
for a,b in similar[:20]:
    print('-', a, '==', b)

print('\nFim da checagem')
