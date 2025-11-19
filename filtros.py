import re

# Palavras-chave relacionadas a tecnologia
KEYWORDS_TECNOLOGIA = [
    'tecnologia', 'software', 'hardware', 'programação', 'app', 'aplicativo',
    'smartphone', 'celular', 'computador', 'internet', 'inteligência artificial',
    'ia', 'robô', 'algoritmo', 'cyber', 'digital', 'gadget', 'dispositivo',
    'sistema operacional', 'windows', 'apple', 'android', 'ios', 'código',
    'desenvolvedor', 'programador', 'startup', 'inovação', 'rede', 'wifi',
    'processador', 'chip', 'memória', 'ssd', 'hd', 'placa', 'dados'
]

# Palavras-chave relacionadas a jogos
KEYWORDS_JOGOS = [
    'game', 'jogo', 'gaming', 'console', 'playstation', 'xbox', 'nintendo',
    'ps4', 'ps5', 'steam', 'esports', 'e-sports', 'competitivo', 'torneio',
    'campeonato', 'league of legends', 'lol', 'dota', 'cs:', 'counter-strike',
    'valorant', 'overwatch', 'fortnite', 'pubg', 'battle royale', 'rpg',
    'mmorpg', 'dlc', 'expansão', 'patch', 'atualização', 'gameplay',
    'streamer', 'twitch', 'gamer', 'jogador', 'multiplayer', 'singleplayer'
]

def eh_noticia_relevante(titulo: str, texto: str = '', resumo: str = '') -> bool:
    """
    Verifica se uma notícia é sobre tecnologia ou jogos baseado em suas palavras-chave.
    
    Args:
        titulo: Título da notícia
        texto: Texto completo da notícia (opcional)
        resumo: Resumo da notícia (opcional)
    
    Returns:
        bool: True se a notícia é sobre tecnologia ou jogos, False caso contrário
    """
    # Junta todo o texto disponível em lowercase para busca
    conteudo = f"{titulo} {resumo} {texto}".lower()
    
    # Procura por palavras-chave de tecnologia
    for keyword in KEYWORDS_TECNOLOGIA:
        if keyword.lower() in conteudo:
            return True
    
    # Procura por palavras-chave de jogos
    for keyword in KEYWORDS_JOGOS:
        if keyword.lower() in conteudo:
            return True
    
    return False