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

# Função para configurar Selenium no Streamlit Cloud
@st.cache_resource
def setup_driver():
    """Configura o driver do Selenium para Streamlit Cloud"""
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--single-process")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Para Streamlit Cloud
        chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")
        
        driver = webdriver.Chrome(
            executable_path=os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"),
            options=chrome_options
        )
        return driver
    except Exception as e:
        st.error(f"Erro ao configurar Chrome: {e}")
        return None

# Método alternativo usando requests + BeautifulSoup
def extract_with_requests(url, max_videos=20):
    """Método alternativo usando requests (para quando Selenium não funciona)"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Referer': 'https://artlist.io/',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin'
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
        
        # Seletores mais específicos do Artlist
        video_selectors = [
            # Seletores específicos do Artlist (baseado no debug)
            '[data-testid*="clip"]',
            '[data-testid*="video"]', 
            '[class*="ClipCard"]',
            '[class*="VideoCard"]',
            '[class*="MediaCard"]',
            'article[class*="clip"]',
            'div[class*="clip"]',
            # Novos seletores baseados na estrutura real
            'div[class*="grid"] > div',
            'div[class*="list"] > div', 
            'div[class*="item"]',
            'div[role="article"]',
            'div[role="listitem"]',
            # Seletores por conteúdo
            'div:has(> a[href*="/stock-footage/"])',
            'div:has(> a[href*="/clip/"])',
            'div:has(img)',
            # Seletores genéricos
            '.video-item',
            '.clip-item',
            '[class*="video"]',
            '[class*="clip"]',
            'article',
            '.grid-item'
        ]
        
        video_elements = []
        elements_found = {}
        
        for selector in video_selectors:
            try:
                elements = soup.select(selector)
                elements_found[selector] = len(elements)
                if elements and len(elements) > 0:
                    st.info(f"✅ Encontrados {len(elements)} elementos com seletor: {selector}")
                    video_elements = elements[:max_videos]
                    break
            except Exception as e:
                st.warning(f"❌ Erro com seletor {selector}: {e}")
                continue
        
        # Debug: mostrar seletores testados
        with st.expander("🔧 Debug - Seletores testados"):
            for selector, count in elements_found.items():
                st.write(f"- `{selector}`: {count} elementos")
        
        if not video_elements:
            st.warning("⚠️ Usando fallback: procurando divs com imagens...")
            # Fallback mais agressivo - buscar qualquer div que tenha link para artlist
            all_divs = soup.find_all(['div', 'article', 'section', 'li'])
            video_elements = []
            
            for div in all_divs:
                # Verificar se tem imagem OU link para vídeo OU texto que parece título
                has_content = (
                    div.find('img') or 
                    div.find('video') or
                    div.find('a', href=lambda x: x and ('/stock-footage/' in x or '/clip/' in x)) or
                    (div.get_text(strip=True) and len(div.get_text(strip=True)) > 10)
                )
                
                if has_content:
                    video_elements.append(div)
                    
                if len(video_elements) >= max_videos * 2:  # Pegar mais elementos para filtrar depois
                    break
        
        # Se ainda não encontrou nada, pegar todos os divs com qualquer conteúdo
        if not video_elements:
            st.warning("⚠️ Fallback extremo: analisando todos os elementos...")
            all_elements = soup.find_all(['div', 'section', 'article'])
            video_elements = [el for el in all_elements if el.get_text(strip=True)][:max_videos * 3]
        
        st.info(f"🎯 Processando {len(video_elements)} elementos encontrados...")
        
        processed_count = 0
        for i, element in enumerate(video_elements[:max_videos * 2]):  # Processar mais elementos
            video_data = extract_video_from_element(element, i, soup)
            if video_data and (video_data.get('Title') or video_data.get('Video URL') or video_data.get('Thumbnail URL')):
                df_data.append(video_data)
                processed_count += 1
                st.success(f"✅ Vídeo {processed_count} extraído: {video_data.get('Title', 'Sem título')[:50]}...")
                
                if processed_count >= max_videos:  # Parar quando atingir o limite desejado
                    break
            else:
                if i < 5:  # Mostrar debug só dos primeiros elementos
                    st.warning(f"⚠️ Elemento {i+1} não teve dados válidos extraídos")
        
        return df_data
        
    except Exception as e:
        st.error(f"Erro na extração com requests: {e}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def generate_thumbnail_from_title(title, video_id):
    """Gera thumbnail baseado no título do vídeo"""
    if not title:
        return generate_placeholder_thumbnail()
    
    try:
        # Extrair palavras-chave do título
        keywords = extract_keywords_from_title(title)
        
        # Tentar buscar imagem no Unsplash
        unsplash_url = get_unsplash_image(keywords)
        if unsplash_url:
            return unsplash_url
        
        # Fallback: usar Picsum (imagens aleatórias)
        return f"https://picsum.photos/400/225?random={hash(video_id) % 1000}"
        
    except Exception as e:
        st.warning(f"Erro ao gerar thumbnail: {e}")
        return generate_placeholder_thumbnail()

def extract_keywords_from_title(title):
    """Extrai palavras-chave relevantes do título"""
    # Remover palavras comuns e caracteres especiais
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'new', 'old'}
    
    # Limpar título
    clean_title = re.sub(r'[^\w\s]', ' ', title.lower())
    words = [word.strip() for word in clean_title.split() if word.strip() and word not in stop_words]
    
    # Pegar as 2-3 palavras mais relevantes
    relevant_words = words[:3]
    
    return ' '.join(relevant_words) if relevant_words else 'nature'

def get_unsplash_image(keywords):
    """Busca imagem no Unsplash baseada nas palavras-chave"""
    try:
        # URL da API do Unsplash (acesso público limitado)
        url = f"https://source.unsplash.com/400x225/?{keywords.replace(' ', ',')}"
        
        # Testar se a URL responde
        response = requests.head(url, timeout=5)
        if response.status_code == 200:
            return url
        
    except:
        pass
    
    return None

def generate_placeholder_thumbnail():
    """Gera thumbnail placeholder"""
    return "https://via.placeholder.com/400x225/4299ff/ffffff?text=Artlist+Video"

def generate_smart_thumbnail(title, video_url, video_id):
    """Gera thumbnail inteligente baseado no contexto"""
    
    # 1. Tentar extrair da própria URL do vídeo
    if video_url:
        try:
            # Algumas URLs do Artlist têm padrões previsíveis para thumbnails
            if 'artlist.io' in video_url:
                # Tentar construir URL de thumbnail baseada na URL do vídeo
                video_path = video_url.replace('https://artlist.io/', '')
                
                # Padrões comuns de thumbnail no Artlist
                possible_thumbnails = [
                    f"https://artlist.io/thumb/{video_path.split('/')[-1]}.jpg",
                    f"https://artlist.io/thumbnails/{video_path.split('/')[-1]}.jpg",
                    f"https://artlist.io/images/{video_path.split('/')[-1]}.jpg"
                ]
                
                for thumb_url in possible_thumbnails:
                    try:
                        response = requests.head(thumb_url, timeout=3)
                        if response.status_code == 200:
                            return thumb_url
                    except:
                        continue
        except:
            pass
    
    # 2. Gerar baseado no título
    return generate_thumbnail_from_title(title, video_id)

# Categoria de thumbnails baseada no título
def get_thumbnail_category(title):
    """Determina categoria da thumbnail baseada no título"""
    title_lower = title.lower()
    
    categories = {
        'nature': ['safari', 'africa', 'wildlife', 'animal', 'forest', 'tree', 'mountain', 'ocean', 'beach'],
        'city': ['urban', 'city', 'building', 'street', 'downtown', 'skyline'],
        'people': ['person', 'people', 'man', 'woman', 'child', 'family', 'group'],
        'business': ['office', 'meeting', 'work', 'business', 'corporate', 'professional'],
        'technology': ['tech', 'computer', 'digital', 'code', 'data', 'AI', 'robot'],
        'food': ['food', 'cooking', 'kitchen', 'restaurant', 'meal', 'chef'],
        'travel': ['travel', 'vacation', 'tourism', 'destination', 'journey'],
        'abstract': ['abstract', 'pattern', 'texture', 'background', 'design']
    }
    
    for category, keywords in categories.items():
        if any(keyword in title_lower for keyword in keywords):
            return category
    
    return 'nature'  # padrão
    """Extrai dados de um elemento HTML"""
    try:
        # ID - mais variações
        video_id = (element.get('data-id') or 
                   element.get('data-video-id') or
                   element.get('data-clip-id') or
                   element.get('data-testid') or
                   element.get('id') or 
                   f"video_{index}_{int(time.time())}")
        
        # Título - seletores mais abrangentes
        title_selectors = [
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            '.title', '[class*="title" i]', '[class*="Title" i]',
            '.name', '[class*="name" i]', '[class*="Name" i]',
            '.label', '[class*="label" i]',
            'span[class*="text"]', 'div[class*="text"]',
            'p', 'span', 'div'
        ]
        
        title = ""
        title_candidates = []
        
        for selector in title_selectors:
            try:
                title_elems = element.select(selector)
                for elem in title_elems:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 3 and len(text) < 200:  # Filtrar textos muito curtos/longos
                        title_candidates.append(text)
            except:
                continue
        
        # Pegar o primeiro candidato válido
        if title_candidates:
            title = title_candidates[0]
        
        # Se não achou título, tentar alt text das imagens
        if not title:
            try:
                img = element.find('img')
                if img and img.get('alt'):
                    title = img.get('alt').strip()
            except:
                pass
        
        # Descrição - buscar em vários lugares
        desc_selectors = [
            '.description', '[class*="description" i]',
            '.summary', '[class*="summary" i]',
            '.excerpt', '[class*="excerpt" i]',
            'p', '.text', '[class*="text" i]'
        ]
        
        description = ""
        desc_candidates = []
        
        for selector in desc_selectors:
            try:
                desc_elems = element.select(selector)
                for elem in desc_elems:
                    text = elem.get_text(strip=True)
                    if text and text != title and len(text) > 10:
                        desc_candidates.append(text)
            except:
                continue
        
        if desc_candidates:
            description = desc_candidates[0][:500]  # Limitar tamanho
        
        # URL do vídeo - buscar links
        video_url = ""
        
        # Primeiro, tentar links diretos
        links = element.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            if href:
                if href.startswith('/'):
                    video_url = urljoin('https://artlist.io', href)
                elif 'artlist.io' in href:
                    video_url = href
                elif href.startswith('http'):
                    video_url = href
                
                if video_url:
                    break
        
        # Se não achou, tentar data attributes
        if not video_url:
            for attr in ['data-url', 'data-link', 'data-href']:
                url_attr = element.get(attr)
                if url_attr:
                    if url_attr.startswith('/'):
                        video_url = urljoin('https://artlist.io', url_attr)
                    else:
                        video_url = url_attr
                    break
        
        # Thumbnail - buscar imagens com mais variações
        thumbnail_url = ""
        
        # 1. Buscar img tags com diferentes atributos
        img_elem = element.find('img')
        if img_elem:
            thumbnail_url = (img_elem.get('src') or 
                           img_elem.get('data-src') or 
                           img_elem.get('data-original') or
                           img_elem.get('data-lazy') or
                           img_elem.get('data-srcset') or
                           img_elem.get('srcset', '').split(',')[0].strip().split(' ')[0] or
                           "")
        
        # 2. Se não achou img, buscar picture > source
        if not thumbnail_url:
            picture = element.find('picture')
            if picture:
                source = picture.find('source')
                if source:
                    thumbnail_url = source.get('srcset', '').split(',')[0].strip().split(' ')[0]
        
        # 3. Buscar background-image em qualquer elemento filho
        if not thumbnail_url:
            for child in element.find_all():
                style = child.get('style', '')
                if 'background-image' in style:
                    import re
                    match = re.search(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
                    if match:
                        thumbnail_url = match.group(1)
                        break
        
        # 4. Buscar em data attributes relacionados a imagem
        if not thumbnail_url:
            for attr in ['data-bg', 'data-background', 'data-image', 'data-thumb', 'data-poster']:
                thumb_attr = element.get(attr)
                if thumb_attr:
                    thumbnail_url = thumb_attr
                    break
        
        # Ajustar URLs relativas
        if thumbnail_url and thumbnail_url.startswith('/'):
            thumbnail_url = urljoin('https://artlist.io', thumbnail_url)
        
        # 🆕 Se não encontrou thumbnail, gerar uma inteligente
        if not thumbnail_url:
            thumbnail_url = generate_smart_thumbnail(title, video_url, video_id)
        
        # Idioma - detecção melhorada
        language = "en"
        text_content = f"{title} {description}".lower()
        
        # Palavras-chave para detecção de idioma
        pt_keywords = [
            'português', 'brasil', 'pt-br', 'brasileiro', 'lusitano',
            'música', 'vídeo', 'imagem', 'som', 'áudio'
        ]
        
        if any(keyword in text_content for keyword in pt_keywords):
            language = "pt"
        
        # Debug info - incluir informações sobre URLs encontradas
        debug_info = {
            'element_tag': element.name,
            'element_classes': element.get('class', []),
            'title_candidates': title_candidates[:3],
            'desc_candidates': desc_candidates[:2] if desc_candidates else [],
            'all_urls_found': debug_urls,
            'selected_video_url': video_url,
            'extracted_id': video_id,
            'links_found': len(all_links),
            'has_img': bool(img_elem)
        }
        
        result = {
            'ID': str(video_id),
            'Source': 'artlist.io',
            'Title': title,
            'Description': description,
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': language,
            '_debug': debug_info  # Para debug, será removido depois
        }
        
        return result
        
    except Exception as e:
        st.error(f"Erro ao extrair elemento {index}: {e}")
        return None

def extract_with_selenium(driver, url, max_videos):
    """Extração usando Selenium"""
    df_data = []
    
    try:
        driver.get(url)
        time.sleep(5)
        
        # Aceitar cookies
        try:
            cookie_selectors = [
                "//button[contains(text(), 'Accept')]",
                "//button[contains(text(), 'aceitar')]",
                "//button[contains(@class, 'cookie')]",
                "[data-testid='accept-cookies']"
            ]
            
            for selector in cookie_selectors:
                try:
                    if selector.startswith('//'):
                        button = driver.find_element(By.XPATH, selector)
                    else:
                        button = driver.find_element(By.CSS_SELECTOR, selector)
                    button.click()
                    time.sleep(2)
                    break
                except:
                    continue
        except:
            pass
        
        # Scroll e coleta
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        for scroll in range(5):  # Limitar scrolls para o cloud
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Encontrar elementos de vídeo
        video_selectors = [
            '[data-testid*="video"]',
            '.video-item',
            '.clip-item',
            '[class*="video"]'
        ]
        
        video_elements = []
        for selector in video_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    video_elements = elements[:max_videos]
                    break
            except:
                continue
        
        for i, element in enumerate(video_elements):
            try:
                video_data = extract_selenium_element(element, i)
                if video_data:
                    df_data.append(video_data)
            except:
                continue
        
        return df_data
        
    except Exception as e:
        st.error(f"Erro no Selenium: {e}")
        return []

def extract_selenium_element(element, index):
    """Extrai dados de elemento Selenium"""
    try:
        video_id = (element.get_attribute('data-id') or 
                   element.get_attribute('id') or 
                   f"video_{index}")
        
        # Título
        title = ""
        title_selectors = ['h3', 'h4', '.title', '[class*="title"]']
        for selector in title_selectors:
            try:
                title_elem = element.find_element(By.CSS_SELECTOR, selector)
                title = title_elem.text.strip()
                if title:
                    break
            except:
                continue
        
        # URL
        video_url = ""
        try:
            link = element.find_element(By.TAG_NAME, 'a')
            href = link.get_attribute('href')
            if href:
                video_url = href
        except:
            pass
        
        # Thumbnail
        thumbnail_url = ""
        try:
            img = element.find_element(By.TAG_NAME, 'img')
            thumbnail_url = img.get_attribute('src') or ""
        except:
            pass
        
        return {
            'ID': video_id,
            'Source': 'artlist.io',
            'Title': title,
            'Description': "",
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': "en"
        }
        
    except:
        return None

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
            max_value=50,  # Limitado para cloud
            value=20,
            help="Máximo de vídeos (limitado no cloud)"
        )
    
    # Método de extração e opções de thumbnail
    col1, col2 = st.columns(2)
    
    with col1:
        method = st.radio(
            "Método de extração:",
            ["Requests + BeautifulSoup (Recomendado)", "Selenium (Experimental)"],
            help="Requests é mais estável no Streamlit Cloud"
        )
    
    with col2:
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
        
        # Validar URL
        if 'artlist.io' not in url_input:
            st.error("❌ A URL deve ser do domínio artlist.io")
            return
        
        # Mostrar URL que será processada
        st.info(f"🌐 Processando URL: {url_input}")
        
        with st.spinner("Extraindo dados..."):
            if method.startswith("Requests"):
                df_data = extract_with_requests(url_input, max_videos)
            else:
                driver = setup_driver()
                if driver:
                    try:
                        df_data = extract_with_selenium(driver, url_input, max_videos)
                    finally:
                        driver.quit()
                else:
                    st.error("Selenium não disponível. Use o método Requests.")
                    return
        
        # Pós-processar thumbnails se necessário
        if df_data and thumbnail_option != "Gerar baseada no título":
            with st.spinner("🎨 Gerando thumbnails..."):
                for item in df_data:
                    if not item.get('Thumbnail URL'):
                        if thumbnail_option == "Usar placeholder padrão":
                            item['Thumbnail URL'] = generate_placeholder_thumbnail()
                        elif thumbnail_option == "Buscar no Unsplash":
                            item['Thumbnail URL'] = get_unsplash_image(item.get('Title', 'video')) or generate_placeholder_thumbnail()
                        elif thumbnail_option == "Imagens aleatórias (Picsum)":
                            seed = abs(hash(item.get('ID', 'default'))) % 1000
                            item['Thumbnail URL'] = f"https://picsum.photos/400/225?random={seed}"
        
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
            
            # Amostra com debug
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
                    # Remover debug info antes de mostrar
                    clean_sample = {k: v for k, v in sample.items() if not k.startswith('_')}
                    st.json(clean_sample)
                
                # Mostrar info de debug se disponível
                if '_debug' in sample:
                    with st.expander("🔧 Debug Info"):
                        st.json(sample['_debug'])
                
                # Limpar debug info dos dados finais
                for item in df_data:
                    item.pop('_debug', None)
        
        else:
            st.warning("❌ Nenhum vídeo encontrado")
            st.info("💡 Tente uma URL específica de busca do Artlist")

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
