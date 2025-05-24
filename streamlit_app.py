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
            # Seletores específicos do Artlist
            '[data-testid*="clip"]',
            '[data-testid*="video"]', 
            '[class*="ClipCard"]',
            '[class*="VideoCard"]',
            '[class*="MediaCard"]',
            'article[class*="clip"]',
            'div[class*="clip"]',
            # Seletores genéricos
            '.video-item',
            '.clip-item',
            '[class*="video"]',
            '[class*="clip"]',
            'article',
            '.grid-item',
            # Fallback para qualquer div com imagem
            'div:has(img)',
            'section:has(img)'
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
            # Fallback mais agressivo
            all_divs = soup.find_all(['div', 'article', 'section'])
            video_elements = []
            for div in all_divs:
                if div.find('img') or div.find('video') or 'video' in str(div.get('class', [])).lower():
                    video_elements.append(div)
                if len(video_elements) >= max_videos:
                    break
        
        st.info(f"🎯 Processando {len(video_elements)} elementos encontrados...")
        
        for i, element in enumerate(video_elements[:max_videos]):
            video_data = extract_video_from_element(element, i, soup)
            if video_data:
                df_data.append(video_data)
                st.success(f"✅ Vídeo {i+1} extraído: {video_data.get('Title', 'Sem título')}")
            else:
                st.warning(f"⚠️ Não foi possível extrair dados do elemento {i+1}")
        
        return df_data
        
    except Exception as e:
        st.error(f"Erro na extração com requests: {e}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def extract_video_from_element(element, index, soup=None):
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
        
        # Thumbnail - buscar imagens
        thumbnail_url = ""
        
        # Buscar img tags
        img_elem = element.find('img')
        if img_elem:
            thumbnail_url = (img_elem.get('src') or 
                           img_elem.get('data-src') or 
                           img_elem.get('data-original') or
                           img_elem.get('srcset', '').split(',')[0].strip().split(' ')[0] or
                           "")
        
        # Se não achou img, buscar background-image
        if not thumbnail_url:
            style = element.get('style', '')
            if 'background-image' in style:
                import re
                match = re.search(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
                if match:
                    thumbnail_url = match.group(1)
        
        # Ajustar URLs relativas
        if thumbnail_url and thumbnail_url.startswith('/'):
            thumbnail_url = urljoin('https://artlist.io', thumbnail_url)
        
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
        
        # Debug info
        debug_info = {
            'element_tag': element.name,
            'element_classes': element.get('class', []),
            'title_candidates': title_candidates[:3],
            'desc_candidates': desc_candidates[:2] if desc_candidates else [],
            'links_found': len(links),
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
            value="https://artlist.io/stock-footage/search",
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
    
    # Método de extração
    method = st.radio(
        "Método de extração:",
        ["Requests + BeautifulSoup (Recomendado)", "Selenium (Experimental)"],
        help="Requests é mais estável no Streamlit Cloud"
    )
    
    if st.button("🚀 Extrair Vídeos", type="primary"):
        if not url_input:
            st.error("Insira uma URL válida")
            return
        
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
