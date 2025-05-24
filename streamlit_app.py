import streamlit as st
import pandas as pd
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
from urllib.parse import urljoin, urlparse
import json

# Configuração da página
st.set_page_config(
    page_title="Extrator de Vídeos Artlist",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 Extrator de Vídeos do Artlist")
st.markdown("Extraia dados de vídeos do Artlist.io de forma automatizada")

# Função para configurar o driver do Selenium
@st.cache_resource
def setup_driver():
    """Configura e retorna o driver do Selenium"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Executar em modo headless
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Erro ao configurar o Chrome WebDriver: {e}")
        st.info("Certifique-se de que o ChromeDriver está instalado e no PATH")
        return None

def extract_video_data(driver, url, max_videos=50):
    """Extrai dados dos vídeos da página"""
    df_data = []
    
    try:
        # Navegar para a URL
        driver.get(url)
        time.sleep(5)
        
        # Aguardar o carregamento do conteúdo
        wait = WebDriverWait(driver, 20)
        
        # Tentar aceitar cookies se aparecer o modal
        try:
            cookie_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept') or contains(text(), 'aceitar') or contains(@class, 'cookie')]")))
            cookie_button.click()
            time.sleep(2)
        except:
            pass
        
        # Scroll para carregar mais vídeos
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        max_scroll_attempts = 10
        
        while scroll_attempts < max_scroll_attempts and len(df_data) < max_videos:
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            # Aguardar novo conteúdo carregar
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
            
            last_height = new_height
            
            # Tentar encontrar elementos de vídeo
            video_containers = driver.find_elements(By.CSS_SELECTOR, 
                "[data-testid*='video'], .video-item, .clip-item, [class*='video'], [class*='clip']")
            
            st.write(f"Encontrados {len(video_containers)} containers de vídeo")
            
            for i, container in enumerate(video_containers[:max_videos]):
                if len(df_data) >= max_videos:
                    break
                    
                try:
                    video_data = extract_single_video_data(container, driver, i)
                    if video_data and video_data not in df_data:
                        df_data.append(video_data)
                        
                except Exception as e:
                    st.write(f"Erro ao extrair vídeo {i}: {e}")
                    continue
        
        return df_data
        
    except Exception as e:
        st.error(f"Erro durante a extração: {e}")
        return df_data

def extract_single_video_data(container, driver, index):
    """Extrai dados de um único vídeo"""
    try:
        # Tentar extrair ID (pode estar em atributos data-* ou na URL)
        video_id = None
        for attr in ['data-id', 'data-video-id', 'data-clip-id', 'id']:
            video_id = container.get_attribute(attr)
            if video_id:
                break
        
        if not video_id:
            video_id = f"video_{index}_{int(time.time())}"
        
        # Tentar extrair título
        title_selectors = [
            'h3', 'h4', '.title', '[class*="title"]', 
            '.clip-title', '[data-testid*="title"]'
        ]
        title = ""
        for selector in title_selectors:
            try:
                title_element = container.find_element(By.CSS_SELECTOR, selector)
                title = title_element.text.strip()
                if title:
                    break
            except:
                continue
        
        # Tentar extrair descrição
        description_selectors = [
            '.description', '[class*="description"]', 
            '.clip-description', 'p'
        ]
        description = ""
        for selector in description_selectors:
            try:
                desc_element = container.find_element(By.CSS_SELECTOR, selector)
                description = desc_element.text.strip()
                if description and description != title:
                    break
            except:
                continue
        
        # Tentar extrair URL do vídeo
        video_url = ""
        link_selectors = ['a', '[href]']
        for selector in link_selectors:
            try:
                link_element = container.find_element(By.CSS_SELECTOR, selector)
                href = link_element.get_attribute('href')
                if href and ('artlist.io' in href or href.startswith('/')):
                    if href.startswith('/'):
                        video_url = urljoin('https://artlist.io/', href)
                    else:
                        video_url = href
                    break
            except:
                continue
        
        # Tentar extrair thumbnail
        thumbnail_url = ""
        img_selectors = ['img', 'video', '[style*="background-image"]']
        for selector in img_selectors:
            try:
                img_element = container.find_element(By.CSS_SELECTOR, selector)
                if selector == '[style*="background-image"]':
                    style = img_element.get_attribute('style')
                    match = re.search(r'background-image:\s*url\(["\']?([^"\']+)["\']?\)', style)
                    if match:
                        thumbnail_url = match.group(1)
                else:
                    src = img_element.get_attribute('src') or img_element.get_attribute('poster')
                    if src:
                        thumbnail_url = src
                
                if thumbnail_url:
                    break
            except:
                continue
        
        # Detectar idioma (básico)
        language = "en"  # padrão
        if title or description:
            text = f"{title} {description}".lower()
            if any(word in text for word in ['português', 'brasil', 'pt-br']):
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
        st.write(f"Erro ao extrair dados do container: {e}")
        return None

def main():
    # Interface do usuário
    col1, col2 = st.columns([2, 1])
    
    with col1:
        url_input = st.text_input(
            "URL do Artlist:",
            value="https://artlist.io/stock-footage/search",
            help="Cole a URL da página de busca do Artlist"
        )
    
    with col2:
        max_videos = st.number_input(
            "Máximo de vídeos:",
            min_value=1,
            max_value=200,
            value=50,
            help="Número máximo de vídeos para extrair"
        )
    
    # Botão para iniciar extração
    if st.button("🚀 Extrair Vídeos", type="primary"):
        if not url_input:
            st.error("Por favor, insira uma URL válida")
            return
        
        # Validar URL
        if 'artlist.io' not in url_input:
            st.warning("A URL deve ser do domínio artlist.io")
        
        # Configurar driver
        with st.spinner("Configurando navegador..."):
            driver = setup_driver()
        
        if not driver:
            st.stop()
        
        try:
            # Extrair dados
            with st.spinner(f"Extraindo até {max_videos} vídeos... Isso pode levar alguns minutos."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("Carregando página...")
                progress_bar.progress(10)
                
                df_data = extract_video_data(driver, url_input, max_videos)
                progress_bar.progress(100)
                
            # Exibir resultados
            if df_data:
                st.success(f"✅ Extraídos {len(df_data)} vídeos com sucesso!")
                
                # Criar DataFrame
                df = pd.DataFrame(df_data)
                
                # Exibir estatísticas
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total de Vídeos", len(df))
                with col2:
                    st.metric("Com Título", len(df[df['Title'] != '']))
                with col3:
                    st.metric("Com Thumbnail", len(df[df['Thumbnail URL'] != '']))
                
                # Exibir tabela
                st.subheader("📊 Dados Extraídos")
                st.dataframe(df, use_container_width=True)
                
                # Opções de download
                st.subheader("💾 Download")
                col1, col2 = st.columns(2)
                
                with col1:
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="📥 Baixar CSV",
                        data=csv,
                        file_name=f"artlist_videos_{int(time.time())}.csv",
                        mime="text/csv"
                    )
                
                with col2:
                    json_data = df.to_json(orient='records', indent=2)
                    st.download_button(
                        label="📥 Baixar JSON",
                        data=json_data,
                        file_name=f"artlist_videos_{int(time.time())}.json",
                        mime="application/json"
                    )
                
                # Exibir amostra dos dados
                st.subheader("🔍 Amostra dos Dados")
                for i, video in enumerate(df_data[:3]):
                    with st.expander(f"Vídeo {i+1}: {video['Title'][:50]}..."):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            if video['Thumbnail URL']:
                                try:
                                    st.image(video['Thumbnail URL'], width=200)
                                except:
                                    st.write("Thumbnail não disponível")
                        with col2:
                            st.write(f"**ID:** {video['ID']}")
                            st.write(f"**Título:** {video['Title']}")
                            st.write(f"**Descrição:** {video['Description'][:100]}...")
                            st.write(f"**URL:** {video['Video URL']}")
                            st.write(f"**Idioma:** {video['Language']}")
            
            else:
                st.warning("❌ Nenhum vídeo foi encontrado. Verifique se a URL está correta e se a página contém vídeos.")
                st.info("💡 Dica: Tente com uma URL de busca específica do Artlist que contenha resultados de vídeos.")
        
        except Exception as e:
            st.error(f"Erro durante a extração: {e}")
        
        finally:
            # Fechar driver
            try:
                driver.quit()
            except:
                pass

# Informações adicionais
with st.sidebar:
    st.header("ℹ️ Informações")
    st.markdown("""
    ### Como usar:
    1. Cole a URL da página de busca do Artlist
    2. Defina o número máximo de vídeos
    3. Clique em "Extrair Vídeos"
    4. Aguarde a extração (pode levar alguns minutos)
    5. Baixe os dados em CSV ou JSON
    
    ### Requisitos:
    - ChromeDriver instalado
    - Conexão com internet
    - Python com bibliotecas: streamlit, selenium, pandas
    
    ### Instalação:
    ```bash
    pip install streamlit selenium pandas requests
    ```
    
    ### Observações:
    - O processo pode ser lento devido ao carregamento dinâmico
    - Alguns dados podem não estar disponíveis
    - Respeite os termos de uso do site
    """)

if __name__ == "__main__":
    main()
