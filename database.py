import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any

class Database:
    def __init__(self, db_file: str = 'noticias.db'):
        self.db_file = db_file
        
    def get_connection(self):
        # timeout to wait for locks; row_factory para facilitar conversão para dict
        conn = sqlite3.connect(self.db_file, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn
        
    def init_db(self):
        """Inicializa o banco de dados"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Otimizações SQLite
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")

            # Cria a tabela principal sem dropar (preserva dados em produção)
            # removemos DROP TABLE para não apagar dados acidentalmente
            
            # Cria a tabela principal de notícias
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS noticias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link TEXT UNIQUE,
                    feed TEXT DEFAULT '',
                    -- campeonato_slug armazena o slug do campeonato relacionado (se houver)
                    campeonato_slug TEXT DEFAULT '',
                    titulo TEXT DEFAULT '',
                    resumo TEXT DEFAULT '',
                    texto TEXT DEFAULT '',
                    publicado TEXT DEFAULT '',
                    added_at INTEGER DEFAULT 0,
                    imagem_principal TEXT DEFAULT '',
                    imagem_principal_local TEXT DEFAULT ''
                )
            ''')
            # índice para ordenação por data/added_at
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_noticias_added_at ON noticias(added_at)')
            # índice para busca por link (melhora checagem de duplicados)
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_noticias_link ON noticias(link)')
            # Se a coluna campeonato_slug não existir (schema antigo), adiciona via ALTER TABLE
            cursor.execute("PRAGMA table_info(noticias)")
            cols = [r[1] for r in cursor.fetchall()]
            if 'campeonato_slug' not in cols:
                try:
                    cursor.execute("ALTER TABLE noticias ADD COLUMN campeonato_slug TEXT DEFAULT ''")
                    print('Coluna campeonato_slug adicionada à tabela noticias')
                except Exception as e:
                    print(f'Falha ao adicionar coluna campeonato_slug: {e}')
            # índice para consultas por campeonato (acesso rápido em páginas de campeonato)
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_noticias_campeonato ON noticias(campeonato_slug)')
            except Exception as e:
                print(f'Falha ao criar índice de campeonato: {e}')
            
            conn.commit()
            print("Banco de dados inicializado com sucesso!")
            
        except Exception as e:
            print(f"Erro ao inicializar banco de dados: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def save_noticia(self, noticia: Dict[str, Any]) -> bool:
        """Salva uma notícia no banco"""
        if not isinstance(noticia, dict):
            print("Erro: notícia deve ser um dicionário")
            return False
            
        conn = self.get_connection()
        try:
            dados = {
                'link': str(noticia.get('link', '')),
                'feed': str(noticia.get('feed', '')),
                'campeonato_slug': str(noticia.get('campeonato_slug', '')),
                'titulo': str(noticia.get('titulo', '')),
                'resumo': str(noticia.get('resumo', '')),
                'texto': str(noticia.get('texto', '')),
                'publicado': str(noticia.get('publicado', '')),
                'added_at': int(noticia.get('added_at', datetime.now().timestamp())),
                'imagem_principal': str(noticia.get('imagem_principal', '')),
                'imagem_principal_local': str(noticia.get('imagem_principal_local', ''))
            }
            
            cursor = conn.cursor()
            # Usar UPSERT para não perder id existente; preserva registro e atualiza campos
            cursor.execute('''
                INSERT INTO noticias (link, feed, campeonato_slug, titulo, resumo, texto, publicado, added_at, imagem_principal, imagem_principal_local)
                VALUES (:link, :feed, :campeonato_slug, :titulo, :resumo, :texto, :publicado, :added_at, :imagem_principal, :imagem_principal_local)
                ON CONFLICT(link) DO UPDATE SET
                    feed=excluded.feed,
                    campeonato_slug=excluded.campeonato_slug,
                    titulo=excluded.titulo,
                    resumo=excluded.resumo,
                    texto=excluded.texto,
                    publicado=excluded.publicado,
                    added_at=excluded.added_at,
                    imagem_principal=excluded.imagem_principal,
                    imagem_principal_local=excluded.imagem_principal_local
            ''', dados)
            
            conn.commit()
            return True
            
        except Exception as e:
            print(f"Erro ao salvar notícia: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_noticias(self, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Recupera notícias paginadas"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            offset = (page - 1) * per_page
            
            # Busca notícias com paginação
            cursor.execute('''
          SELECT id, link, feed, campeonato_slug, titulo, resumo, texto, publicado, 
              added_at, imagem_principal, imagem_principal_local
                FROM noticias 
                ORDER BY added_at DESC 
                LIMIT ? OFFSET ?
            ''', (per_page, offset))
            
            # Como usamos row_factory, cada row já é dict-like (sqlite3.Row)
            noticias = []
            for row in cursor.fetchall():
                noticia = dict(row)
                # normalizar None para string vazia (evita erros na view)
                for k, v in noticia.items():
                    if v is None:
                        noticia[k] = ''
                noticias.append(noticia)
            
            # Conta total para paginação
            cursor.execute('SELECT COUNT(*) FROM noticias')
            total = cursor.fetchone()[0]
            
            return {
                'noticias': noticias,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'current_page': page
            }
            
        except Exception as e:
            print(f"Erro ao buscar notícias: {e}")
            return {
                'noticias': [],
                'total': 0,
                'pages': 1,
                'current_page': page
            }
        finally:
            conn.close()
    
    def get_noticia_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Recupera uma notícia específica pelo URL"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
          SELECT id, link, feed, campeonato_slug, titulo, resumo, texto, publicado,
              added_at, imagem_principal, imagem_principal_local
                FROM noticias 
                WHERE link = ?
            ''', (url,))
            
            row = cursor.fetchone()
            if row:
                colunas = [col[0] for col in cursor.description]
                noticia = dict(zip(colunas, row))
                for key, value in noticia.items():
                    if value is None:
                        noticia[key] = ''  # Converte None para string vazia
                return noticia
            return None
            
        except Exception as e:
            print(f"Erro ao buscar notícia por URL: {e}")
            return None
        finally:
            conn.close()

    def get_noticias_por_campeonato(self, campeonato_slug: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Recupera notícias filtradas pelo slug do campeonato com paginação."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            offset = (page - 1) * per_page
            cursor.execute('''
                SELECT id, link, feed, campeonato_slug, titulo, resumo, texto, publicado,
                       added_at, imagem_principal, imagem_principal_local
                FROM noticias
                WHERE campeonato_slug = ?
                ORDER BY added_at DESC
                LIMIT ? OFFSET ?
            ''', (campeonato_slug, per_page, offset))

            noticias = []
            for row in cursor.fetchall():
                noticia = dict(row)
                for k, v in noticia.items():
                    if v is None:
                        noticia[k] = ''
                noticias.append(noticia)

            cursor.execute('SELECT COUNT(*) FROM noticias WHERE campeonato_slug = ?', (campeonato_slug,))
            total = cursor.fetchone()[0]

            return {
                'noticias': noticias,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'current_page': page
            }
        except Exception as e:
            print(f"Erro ao buscar notícias por campeonato: {e}")
            return {
                'noticias': [],
                'total': 0,
                'pages': 1,
                'current_page': page
            }
        finally:
            conn.close()

# Cria uma instância global do banco de dados
db = Database()

# Funções de compatibilidade para não quebrar o código existente
def init_db():
    db.init_db()

def save_noticia(noticia):
    return db.save_noticia(noticia)

def get_noticias(page=1, per_page=10):
    return db.get_noticias(page, per_page)

def get_noticia_by_url(url):
    return db.get_noticia_by_url(url)

def get_noticias_por_campeonato(campeonato_slug, page=1, per_page=10):
    return db.get_noticias_por_campeonato(campeonato_slug, page, per_page)