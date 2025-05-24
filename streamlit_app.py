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
        # 1. Buscar links do vídeo - MUITO mais agressivo
        video_url = ""
        video_id = ""
        
        # Primeiro: buscar em TODOS os elementos filhos
        all_links = element.find_all('a', href=True, recursive=True)
        
        # Também buscar no próprio elemento se for um link
        if element.name == 'a' and element.get('href'):
            all_links.append(element)
        
        clip_links = []
        
        # Debug: mostrar TODOS os links encontrados
        debug_links = [link.get('href') for link in all_links[:5]]
        
        # Priorizar links com /clip/
        for link in all_links:
            href = link.get('href', '')
            if '/clip/' in href or '/stock-footage/clip/' in href:
                clip_links.append(href)
        
        # Se não achou clips, pegar outros links do Artlist
        if not clip_links:
            for link in all_links:
                href = link.get('href', '')
                if ('artlist.io' in href or href.startswith('/')) and '/artist/' not in href:
                    if any(pattern in href for pattern in ['/stock-footage/', '/video/', '/media/']):
                        clip_links.append(href)
        
        # Se ainda não achou, aceitar qualquer link que pareça ser de vídeo
        if not clip_links:
            for link in all_links:
                href = link.get('href', '')
                if href and len(href) > 10:  # Links não muito curtos
                    clip_links.append(href)
        
        # Processar melhor link
        if clip_links:
            # Priorizar links com /clip/
            best_link = None
            for link in clip_links:
                if '/clip/' in link:
                    best_link = link
                    break
            
            if not best_link:
                best_link = clip_links[0]
            
            # Construir URL completa
            if best_link.startswith('/'):
                video_url = urljoin('https://artlist.io', best_link)
            elif 'artlist.io' in best_link:
                video_url = best_link
            elif best_link.startswith('http'):
                video_url = best_link
            else:
                video_url = f"https://artlist.io{best_link}" if not best_link.startswith('/') else f"https://artlist.io{best_link}"
            
            # Extrair ID do final da URL - MAIS agressivo
            if video_url:
                # Buscar por qualquer número de 4+ dígitos na URL
                numbers = re.findall(r'\d{4,}', video_url)
                if numbers:
                    video_id = numbers[-1]  # Pegar o último número longo
                else:
                    # Se não achou números longos, pegar qualquer número
                    all_numbers = re.findall(r'\d+', video_url)
                    if all_numbers:
                        video_id = all_numbers[-1]
        
        # Se não conseguiu ID da URL, usar atributos do elemento
        if not video_id:
            for attr in ['data-id', 'data-video-id', 'data-clip-id', 'id']:
                attr_value = element.get(attr)
                if attr_value:
                    # Extrair números do atributo
                    numbers = re.findall(r'\d+', str(attr_value))
                    if numbers:
                        video_id = numbers[-1]
                        break
        
        # Último fallback para ID
        if not video_id:
            video_id = f"video_{index}_{int(time.time())}"
        
        # 2. Buscar título - MAIS agressivo
        title = ""
        
        # Primeiro: tentar extrair da URL se tiver
        if video_url:
            url_parts = video_url.split('/')
            for part in url_parts:
                if part and not part.isdigit() and len(part) > 8 and '-' in part:
                    title = part.replace('-', ' ').title()
                    break
        
        # Se não achou na URL, buscar no HTML
        if not title:
            title_selectors = ['h1', 'h2', 'h3', 'h4', '.title', '[class*="title"]', 'span', 'div', 'p']
            
            for selector in title_selectors:
                try:
                    title_elems = element.select(selector)
                    for elem in title_elems:
                        text = elem.get_text(strip=True)
                        if text and len(text) > 5 and len(text) < 200:
                            title = text
                            break
                    if title:
                        break
                except:
                    continue
        
        # Último fallback: alt da imagem
        if not title:
            img = element.find('img')
            if img and img.get('alt'):
                title = img.get('alt').strip()
        
        # 3. Buscar thumbnail - mais opções
        thumbnail_url = ""
        
        # Buscar todas as imagens no elemento
        all_imgs = element.find_all('img')
        for img in all_imgs:
            src = (img.get('src') or 
                   img.get('data-src') or 
                   img.get('data-original') or
                   img.get('data-lazy') or
                   "")
            if src:
                thumbnail_url = src
                break
        
        if thumbnail_url and thumbnail_url.startswith('/'):
        if thumbnail_url and thumbnail_url.startswith('/'):
            thumbnail_url = urljoin('https://artlist.io', thumbnail_url)
        
        # Se não encontrou thumbnail real, gerar uma
        if not thumbnail_url:
            thumbnail_url = generate_smart_thumbnail(title, video_url, video_id)
        
        # Debug info para o primeiro elemento
        debug_info = {
            'all_links_found': debug_links,
            'clip_links': clip_links[:3],
            'selected_url': video_url,
            'extracted_id': video_id,
            'title_source': 'URL' if video_url and title else 'HTML'
        }
        
        result = {
            'ID': str(video_id),
            'Source': 'artlist.io',
            'Title': title,
            'Description': f"Links encontrados: {len(all_links)}, Clip links: {len(clip_links)}",
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': 'en'
        }
        
        # Debug para o primeiro elemento
        if index == 0:
            st.info("🔍 **Debug do primeiro elemento:**")
            st.json(debug_info)
        
        return result
        
    except Exception as e:
        st.error(f"Erro ao extrair elemento {index}: {e}")
        return None
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
        with st.expander("🔧 Debug - HTML (primeiros 2000 chars)"):
            st.text(response.text[:2000])
        
        # Debug: procurar por padrões específicos no HTML
        clip_urls_in_html = re.findall(r'href="([^"]*(?:/clip/|/stock-footage/)[^"]*)"', response.text)
        
        # 🆕 BUSCAR ESPECIFICAMENTE POR CLIP IDs na página
        clip_ids_in_html = re.findall(r'Clip ID["\s:]*(\d{4,})', response.text, re.IGNORECASE)
        if not clip_ids_in_html:
            # Buscar por outros padrões de ID
            clip_ids_in_html = re.findall(r'clip["\s_-]*id["\s:]*(\d{4,})', response.text, re.IGNORECASE)
        if not clip_ids_in_html:
            # Buscar por IDs em data attributes
            clip_ids_in_html = re.findall(r'data-id["\s:]*["\'](\d{4,})["\']', response.text)
        if not clip_ids_in_html:
            # Buscar por qualquer sequência de 6-8 dígitos (padrão comum de IDs do Artlist)
            clip_ids_in_html = re.findall(r'\b(\d{6,8})\b', response.text)
        
        st.info(f"🆔 IDs de clip encontrados: {len(clip_ids_in_html)}")
        if clip_ids_in_html:
            st.success("✅ IDs encontrados!")
            for i, clip_id in enumerate(set(clip_ids_in_html[:5])):  # Remove duplicatas
                st.write(f"   {i+1}. ID: {clip_id}")
        
        st.info(f"🔍 URLs de clip encontradas no HTML: {len(clip_urls_in_html)}")
        
        if clip_urls_in_html:
            st.success("✅ Links de vídeo encontrados no HTML!")
            for i, url in enumerate(clip_urls_in_html[:3]):
                st.write(f"   {i+1}. {url}")
        else:
            st.warning("⚠️ Nenhum link de clip encontrado no HTML - pode ser carregamento dinâmico")
        
        # 🆕 Se encontrou IDs e URLs, combinar os dados
        if clip_ids_in_html and clip_urls_in_html:
            st.info("🎯 Combinando IDs e URLs encontrados...")
            unique_ids = list(set(clip_ids_in_html))[:max_videos]
            
            for i, clip_id in enumerate(unique_ids):
                # Tentar encontrar URL correspondente ou usar a primeira disponível
                corresponding_url = None
                for url in clip_urls_in_html:
                    if clip_id in url:
                        corresponding_url = url
                        break
                
                if not corresponding_url and clip_urls_in_html:
                    corresponding_url = clip_urls_in_html[min(i, len(clip_urls_in_html)-1)]
                
                # Construir URL completa
                if corresponding_url:
                    if corresponding_url.startswith('/'):
                        full_url = urljoin('https://artlist.io', corresponding_url)
                    else:
                        full_url = corresponding_url
                else:
                    # Construir URL baseada no padrão do Artlist
                    full_url = f"https://artlist.io/stock-footage/clip/video-{clip_id}/{clip_id}"
                
                # Extrair título da URL ou criar um baseado no ID
                title = ""
                if corresponding_url:
                    url_parts = corresponding_url.split('/')
                    for part in url_parts:
                        if part and not part.isdigit() and len(part) > 5 and '-' in part:
                            title = part.replace('-', ' ').title()
                            break
                
                if not title:
                    title = f"Artlist Clip {clip_id}"
                
                video_data = {
                    'ID': str(clip_id),
                    'Source': 'artlist.io',
                    'Title': title,
                    'Description': f"Clip extraído do HTML - ID: {clip_id}",
                    'Video URL': full_url,
                    'Thumbnail URL': generate_smart_thumbnail(title, full_url, clip_id),
                    'Language': 'en'
                }
                
                df_data.append(video_data)
                st.success(f"✅ Vídeo {len(df_data)}: {title} (ID: {clip_id})")
            
            return df_data
        
        # Se só encontrou URLs (método anterior)
        elif clip_urls_in_html:
            st.info("🎯 Criando elementos baseados nas URLs encontradas...")
            for i, url in enumerate(clip_urls_in_html[:max_videos]):
                # Extrair ID da URL
                url_parts = url.rstrip('/').split('/')
                video_id = None
                for part in reversed(url_parts):
                    if part.isdigit() and len(part) >= 4:
                        video_id = part
                        break
                
                if not video_id:
                    video_id = f"extracted_{i}"
                
                # Extrair título da URL
                title = ""
                for part in url_parts:
                    if part and not part.isdigit() and len(part) > 5 and '-' in part:
                        title = part.replace('-', ' ').title()
                        break
                
                # Construir URL completa
                if url.startswith('/'):
                    full_url = urljoin('https://artlist.io', url)
                else:
                    full_url = url
                
                video_data = {
                    'ID': str(video_id),
                    'Source': 'artlist.io',
                    'Title': title,
                    'Description': f"Extraído da URL: {full_url}",
                    'Video URL': full_url,
                    'Thumbnail URL': generate_smart_thumbnail(title, full_url, video_id),
                    'Language': 'en'
                }
                
                df_data.append(video_data)
                st.success(f"✅ Vídeo {len(df_data)}: {title} (ID: {video_id})")
            
            return df_data
        
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
            'div[class*="item"]',
            # Novos seletores mais específicos
            'a[href*="/clip/"]',  # Links diretos para clips
            'a[href*="/stock-footage/clip/"]',  # Links específicos
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
            all_divs = soup.find_all(['div', 'article', 'section', 'li'])
            video_elements = []
            
            for div in all_divs:
                links = div.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    if '/clip/' in href or '/stock-footage/' in href:
                        video_elements.append(div)
                        break
                
                if len(video_elements) >= max_videos * 2:
                    break
            
            # Se ainda não encontrou, pegar divs com imagens
            if not video_elements:
                all_elements = soup.find_all(['div', 'article'])
                for elem in all_elements:
                    if elem.find('img') or elem.find('a'):
                        video_elements.append(elem)
                    if len(video_elements) >= max_videos:
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
