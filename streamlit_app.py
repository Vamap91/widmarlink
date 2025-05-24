import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import urljoin, urlparse
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os

# Configuração da página
st.set_page_config(
    page_title="Extrator de Vídeos Artlist",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 Extrator de Vídeos do Artlist")
st.markdown("Extraia dados de vídeos do Artlist.io - Versão Cloud")

# Função para gerar thumbnails
def generate_smart_thumbnail(title, video_url, video_id):
    """Gera thumbnail inteligente baseado no contexto"""
    if not title:
        return "https://via.placeholder.com/400x225/2196F3/ffffff?text=🎬+Artlist+Video"
    
    try:
        # Extrair palavras-chave do título
        keywords = extract_keywords_from_title(title)
        category = get_thumbnail_category(title)
        
        # URLs por categoria
        thumbnail_options = {
            'nature': f"https://source.unsplash.com/400x225/?{keywords},safari,wildlife",
            'city': f"https://source.unsplash.com/400x225/?{keywords},urban,city",
            'people': f"https://source.unsplash.com/400x225/?{keywords},people,portrait",
            'business': f"https://source.unsplash.com/400x225/?business,office",
            'abstract': f"https://source.unsplash.com/400x225/?abstract,pattern"
        }
        
        url = thumbnail_options.get(category, f"https://source.unsplash.com/400x225/?{keywords}")
        
        # Testar se funciona
        try:
            response = requests.head(url, timeout=3)
            if response.status_code == 200:
                return url
        except:
            pass
        
        # Fallback
        seed = abs(hash(title)) % 1000
        return f"https://picsum.photos/400x225?random={seed}"
        
    except:
        return "https://via.placeholder.com/400x225/2196F3/ffffff?text=🎬+Artlist+Video"

def extract_keywords_from_title(title):
    """Extrai palavras-chave do título"""
    if not title:
        return "video"
    
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'new'}
    clean_title = re.sub(r'[^\w\s]', ' ', title.lower())
    words = [word.strip() for word in clean_title.split() if word.strip() and word not in stop_words]
    return ','.join(words[:3]) if words else 'nature'

def get_thumbnail_category(title):
    """Determina categoria da thumbnail"""
    title_lower = title.lower()
    
    categories = {
        'nature': ['safari', 'africa', 'wildlife', 'animal', 'forest', 'tree', 'mountain', 'ocean'],
        'city': ['urban', 'city', 'building', 'street', 'downtown', 'skyline'],
        'people': ['person', 'people', 'man', 'woman', 'child', 'family'],
        'business': ['office', 'meeting', 'work', 'business', 'corporate'],
        'abstract': ['abstract', 'pattern', 'texture', 'background']
    }
    
    for category, keywords in categories.items():
        if any(keyword in title_lower for keyword in keywords):
            return category
    
    return 'nature'

def extract_video_from_element(element, index):
    """Extrai dados de um elemento HTML"""
    try:
        # 1. Buscar links do vídeo
        video_url = ""
        video_id = ""
        
        all_links = element.find_all('a', href=True)
        clip_links = []
        
        # Priorizar links com /clip/
        for link in all_links:
            href = link.get('href', '')
            if '/clip/' in href or '/stock-footage/clip/' in href:
                clip_links.append(href)
        
        # Se não achou, pegar outros links relevantes
        if not clip_links:
            for link in all_links:
                href = link.get('href', '')
                if any(pattern in href for pattern in ['/stock-footage/', '/video/', '/media/']):
                    if '/artist/' not in href:  # Evitar links de artista
                        clip_links.append(href)
        
        # Processar melhor link
        if clip_links:
            best_link = clip_links[0]
            
            # Construir URL completa
            if best_link.startswith('/'):
                video_url = urljoin('https://artlist.io', best_link)
            elif 'artlist.io' in best_link:
                video_url = best_link
            else:
                video_url = best_link
            
            # Extrair ID do final da URL
            if video_url:
                url_parts = video_url.rstrip('/').split('/')
                for part in reversed(url_parts):
                    if part.isdigit() and len(part) >= 4:  # IDs geralmente têm 4+ dígitos
                        video_id = part
                        break
        
        # Se não conseguiu ID da URL, gerar um
        if not video_id:
            video_id = f"video_{index}_{int(time.time())}"
        
        # 2. Buscar título
        title = ""
        title_selectors = ['h1', 'h2', 'h3', 'h4', '.title', '[class*="title"]', 'span', 'div']
        
        for selector in title_selectors:
            try:
                title_elem = element.select_one(selector)
                if title_elem:
                    text = title_elem.get_text(strip=True)
                    if text and len(text) > 3 and len(text) < 150:
                        title = text
                        break
            except:
                continue
        
        # Se não achou título, tentar extrair da URL
        if not title and video_url:
            url_parts = video_url.split('/')
            for part in url_parts:
                if part and not part.isdigit() and len(part) > 5 and '-' in part:
                    title = part.replace('-', ' ').title()
                    break
        
        # Se ainda não tem título, usar alt da imagem
        if not title:
            img = element.find('img')
            if img and img.get('alt'):
                title = img.get('alt').strip()
        
        # 3. Buscar thumbnail
        thumbnail_url = ""
        img_elem = element.find('img')
        if img_elem:
            thumbnail_url = (img_elem.get('src') or 
                           img_elem.get('data-src') or 
                           img_elem.get('data-original') or
                           "")
        
        if thumbnail_url and thumbnail_url.startswith('/'):
            thumbnail_url = urljoin('https://artlist.io', thumbnail_url)
        
        # Se não encontrou thumbnail, gerar uma
        if not thumbnail_url:
            thumbnail_url = generate_smart_thumbnail(title, video_url, video_id)
        
        # 4. Descrição básica
        description = ""
        desc_elem = element.select_one('.description, p')
        if desc_elem:
            desc_text = desc_elem.get_text(strip=True)
            if desc_text and desc_text != title:
                description = desc_text[:300]
        
        return {
            'ID': str(video_id),
            'Source': 'artlist.io',
            'Title': title,
            'Description': description,
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': 'en'
        }
        
    except Exception as e:
        st.error(f"Erro ao extrair elemento {index}: {e}")
        return None

# Função para configurar Selenium
@st.cache_resource
def setup_driver():
    """Configura o driver do Selenium para Streamlit Cloud"""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Erro ao configurar Chrome: {e}")
        return None

def extract_with_requests(url, max_videos=20):
    """Extração usando requests + BeautifulSoup"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://artlist.io/',
    }
    
    df_data = []
    
    try:
        st.info("🔍 Fazendo requisição para o Artlist...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        st.info(f"📄 Página carregada. Tamanho: {len(response.text)} caracteres")
        
        # Debug: mostrar parte do HTML
        with st.expander("🔧 Debug - HTML (primeiros 1000 chars)"):
            st.text(response.text[:1000])
        
        # Seletores para encontrar elementos de vídeo
        video_selectors = [
            '[data-testid*="clip"]',
            '[data-testid*="video"]',
            'div:has(a[href*="/clip/"])',
            'article:has(a[href*="/clip/"])',
            '[class*="clip"]',
            '[class*="video"]',
            'div:has(img):has(a)',
            'article',
            'div[class*="item"]'
        ]
        
        video_elements = []
        elements_found = {}
        
        for selector in video_selectors:
            try:
                elements = soup.select(selector)
                elements_found[selector] = len(elements)
                if elements:
                    st.info(f"✅ Encontrados {len(elements)} elementos com seletor: {selector}")
                    video_elements = elements[:max_videos * 2]  # Pegar mais para filtrar
                    break
            except Exception as e:
                elements_found[selector] = f"Erro: {e}"
        
        # Debug: mostrar seletores testados
        with st.expander("🔧 Debug - Seletores testados"):
            for selector, count in elements_found.items():
                st.write(f"- `{selector}`: {count}")
        
        # Fallback se não encontrou nada
        if not video_elements:
            st.warning("⚠️ Usando fallback: procurando todos os divs com links...")
            all_divs = soup.find_all(['div', 'article'])
            video_elements = []
            
            for div in all_divs:
                if div.find('a', href=True) or div.find('img'):
                    video_elements.append(div)
                if len(video_elements) >= max_videos * 2:
                    break
        
        st.info(f"🎯 Processando {len(video_elements)} elementos encontrados...")
        
        # Processar elementos
        processed_count = 0
        for i, element in enumerate(video_elements):
            try:
                video_data = extract_video_from_element(element, i)
                
                # Só adicionar se tem dados válidos
                if video_data and (video_data.get('Title') or video_data.get('Video URL')):
                    df_data.append(video_data)
                    processed_count += 1
                    
                    # Debug do primeiro vídeo
                    if processed_count == 1:
                        st.success("🔍 **Primeiro vídeo extraído:**")
                        st.info(f"   • ID: {video_data.get('ID')}")
                        st.info(f"   • URL: {video_data.get('Video URL')}")
                        st.info(f"   • Título: {video_data.get('Title')}")
                    
                    st.success(f"✅ Vídeo {processed_count}: {video_data.get('Title', 'Sem título')[:50]}...")
                    
                    if processed_count >= max_videos:
                        break
                        
            except Exception as e:
                st.warning(f"⚠️ Erro ao processar elemento {i+1}: {e}")
                continue
        
        return df_data
        
    except Exception as e:
        st.error(f"Erro na extração: {e}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def main():
    # Interface
    st.markdown("### 🔧 Configurações")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        url_input = st.text_input(
            "URL do Artlist:",
            value="",
            placeholder="Cole aqui a URL do Artlist (ex: https://artlist.io/stock-footage/search)",
            help="URL da página de busca do Artlist"
        )
    
    with col2:
        max_videos = st.number_input(
            "Máx. vídeos:",
            min_value=1,
            max_value=50,
            value=20,
            help="Máximo de vídeos (limitado no cloud)"
        )
    
    # Opções de thumbnail
    thumbnail_option = st.selectbox(
        "Thumbnails automáticas:",
        [
            "Gerar baseada no título",
            "Usar placeholder padrão", 
            "Buscar no Unsplash",
            "Imagens aleatórias (Picsum)"
        ],
        help="Como gerar thumbnails quando não encontradas"
    )
    
    if st.button("🚀 Extrair Vídeos", type="primary"):
        if not url_input:
            st.error("⚠️ Insira uma URL válida do Artlist")
            st.info("💡 Exemplo: https://artlist.io/stock-footage/search?...")
            return
        
        if 'artlist.io' not in url_input:
            st.error("❌ A URL deve ser do domínio artlist.io")
            return
        
        st.info(f"🌐 Processando URL: {url_input}")
        
        with st.spinner("Extraindo dados..."):
            df_data = extract_with_requests(url_input, max_videos)
        
        if df_data:
            st.success(f"✅ {len(df_data)} vídeos extraídos!")
            
            df = pd.DataFrame(df_data)
            
            # Estatísticas
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total", len(df))
            with col2:
                st.metric("Com Título", len(df[df['Title'] != '']))
            with col3:
                st.metric("Com Thumbnail", len(df[df['Thumbnail URL'] != '']))
            
            # Tabela
            st.dataframe(df, use_container_width=True)
            
            # Downloads
            col1, col2 = st.columns(2)
            with col1:
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 CSV",
                    csv,
                    f"artlist_{int(time.time())}.csv",
                    "text/csv"
                )
            
            with col2:
                json_data = df.to_json(orient='records', indent=2)
                st.download_button(
                    "📥 JSON", 
                    json_data,
                    f"artlist_{int(time.time())}.json",
                    "application/json"
                )
            
            # Amostra
            if len(df_data) > 0:
                st.subheader("📋 Amostra dos Dados")
                sample = df_data[0]
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    if sample['Thumbnail URL']:
                        try:
                            st.image(sample['Thumbnail URL'], width=200)
                        except:
                            st.write("❌ Thumbnail indisponível")
                    else:
                        st.write("❌ Thumbnail não encontrada")
                
                with col2:
                    st.json(sample)
        
        else:
            st.warning("❌ Nenhum vídeo encontrado")
            st.info("💡 Tente uma URL específica de busca do Artlist que contenha resultados")

# Sidebar com informações
with st.sidebar:
    st.header("ℹ️ Streamlit Cloud")
    st.markdown("""
    ### Para usar no GitHub:
    
    1. **Crie um repositório** no GitHub
    2. **Adicione este código** como `app.py`
    3. **Crie `requirements.txt`:**
    ```
    streamlit
    pandas
    requests
    beautifulsoup4
    selenium
    ```
    4. **Deploy no streamlit.io:**
       - Conecte sua conta GitHub
       - Selecione o repositório
       - Deploy automático!
    
    ### ⚠️ Limitações Cloud:
    - Selenium pode não funcionar
    - Use método "Requests" 
    - Máximo 50 vídeos
    - Timeout em 30s
    
    ### 🔗 Links úteis:
    - [Streamlit Cloud](https://streamlit.io)
    - [Docs Deployment](https://docs.streamlit.io/streamlit-community-cloud)
    """)

if __name__ == "__main__":
    main()
