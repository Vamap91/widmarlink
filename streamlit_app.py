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
    }
    
    df_data = []
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Procurar por diferentes padrões de elementos de vídeo
        video_selectors = [
            '[data-testid*="video"]',
            '.video-item',
            '.clip-item', 
            '[class*="video"]',
            '[class*="clip"]',
            'article',
            '.grid-item'
        ]
        
        video_elements = []
        for selector in video_selectors:
            elements = soup.select(selector)
            if elements:
                video_elements.extend(elements[:max_videos])
                break
        
        if not video_elements:
            # Fallback: procurar por qualquer elemento com imagem
            video_elements = soup.find_all(['div', 'article', 'section'], limit=max_videos)
            video_elements = [el for el in video_elements if el.find('img')]
        
        for i, element in enumerate(video_elements[:max_videos]):
            video_data = extract_video_from_element(element, i)
            if video_data:
                df_data.append(video_data)
        
        return df_data
        
    except Exception as e:
        st.error(f"Erro na extração com requests: {e}")
        return []

def extract_video_from_element(element, index):
    """Extrai dados de um elemento HTML"""
    try:
        # ID
        video_id = (element.get('data-id') or 
                   element.get('data-video-id') or 
                   element.get('id') or 
                   f"video_{index}_{int(time.time())}")
        
        # Título
        title_selectors = ['h1', 'h2', 'h3', 'h4', '.title', '[class*="title"]']
        title = ""
        for selector in title_selectors:
            title_elem = element.select_one(selector)
            if title_elem and title_elem.get_text(strip=True):
                title = title_elem.get_text(strip=True)
                break
        
        # Descrição
        desc_selectors = ['.description', '[class*="description"]', 'p']
        description = ""
        for selector in desc_selectors:
            desc_elem = element.select_one(selector)
            if desc_elem and desc_elem.get_text(strip=True) != title:
                description = desc_elem.get_text(strip=True)
                break
        
        # URL do vídeo
        video_url = ""
        link_elem = element.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            if href.startswith('/'):
                video_url = urljoin('https://artlist.io', href)
            elif 'artlist.io' in href:
                video_url = href
        
        # Thumbnail
        thumbnail_url = ""
        img_elem = element.find('img')
        if img_elem:
            thumbnail_url = img_elem.get('src') or img_elem.get('data-src') or ""
            if thumbnail_url and thumbnail_url.startswith('/'):
                thumbnail_url = urljoin('https://artlist.io', thumbnail_url)
        
        # Idioma básico
        language = "en"
        text_content = f"{title} {description}".lower()
        if any(word in text_content for word in ['português', 'brasil', 'pt-br']):
            language = "pt"
        
        return {
            'ID': video_id,
            'Source': 'artlist.io',
            'Title': title,
            'Description': description,
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': language
        }
        
    except Exception as e:
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
            
            # Amostra
            if len(df_data) > 0:
                st.subheader("📋 Amostra")
                sample = df_data[0]
                col1, col2 = st.columns([1, 2])
                with col1:
                    if sample['Thumbnail URL']:
                        try:
                            st.image(sample['Thumbnail URL'], width=200)
                        except:
                            st.write("Thumbnail indisponível")
                with col2:
                    st.json(sample)
        
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
