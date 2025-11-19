import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any

class Database:
    def __init__(self, db_file: str = 'noticias.db'):
        self.db_file = db_file
        
    def get_connection(self):
        return sqlite3.connect(self.db_file)
        
    def init_db(self):
        """Inicializa o banco de dados"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Reseta o banco de dados
            cursor.execute('DROP TABLE IF EXISTS noticias')
            
            # Cria a tabela principal de notícias
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS noticias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link TEXT UNIQUE,
                    feed TEXT DEFAULT '',
                    titulo TEXT DEFAULT '',
                    resumo TEXT DEFAULT '',
                    texto TEXT DEFAULT '',
                    publicado TEXT DEFAULT '',
                    added_at INTEGER DEFAULT 0,
                    imagem_principal TEXT DEFAULT '',
                    imagem_principal_local TEXT DEFAULT ''
                )
            ''')
            
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
                'titulo': str(noticia.get('titulo', '')),
                'resumo': str(noticia.get('resumo', '')),
                'texto': str(noticia.get('texto', '')),
                'publicado': str(noticia.get('publicado', '')),
                'added_at': int(noticia.get('added_at', datetime.now().timestamp())),
                'imagem_principal': str(noticia.get('imagem_principal', '')),
                'imagem_principal_local': str(noticia.get('imagem_principal_local', ''))
            }
            
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO noticias 
                (link, feed, titulo, resumo, texto, publicado, added_at, 
                 imagem_principal, imagem_principal_local)
                VALUES 
                (:link, :feed, :titulo, :resumo, :texto, :publicado, :added_at,
                 :imagem_principal, :imagem_principal_local)
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
                SELECT id, link, feed, titulo, resumo, texto, publicado, 
                       added_at, imagem_principal, imagem_principal_local
                FROM noticias 
                ORDER BY added_at DESC 
                LIMIT ? OFFSET ?
            ''', (per_page, offset))
            
            # Converte resultados em dicionários
            colunas = [col[0] for col in cursor.description]
            noticias = []
            for row in cursor.fetchall():
                noticia = dict(zip(colunas, row))
                for key, value in noticia.items():
                    if value is None:
                        noticia[key] = ''  # Converte None para string vazia
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
                SELECT id, link, feed, titulo, resumo, texto, publicado,
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