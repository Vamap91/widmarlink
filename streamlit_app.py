import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import urljoin, urlparse
import json
import os

# Configuração da página
st.set_page_config(
    page_title="Extrator de Vídeos Artlist",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 Extrator de Vídeos do Artlist")
st.markdown("Extraia dados de vídeos do Artlist.io - Versão Cloud")

def generate_smart_thumbnail(title, video_url, video_id):
    """Gera thumbnail inteligente baseado no contexto"""
    if not title:
        return "https://via.placeholder.com/400x225/2196F3/ffffff?text=🎬+Artlist+Video"
    
    try:
        keywords = extract_keywords_from_title(title)
        category = get_thumbnail_category(title)
        
        thumbnail_options = {
            'nature': f"https://source.unsplash.com/400x225/?{keywords},safari,wildlife",
            'city': f"https://source.unsplash.com/400x225/?{keywords},urban,city",
            'people': f"https://source.unsplash.com/400x225/?{keywords},people,portrait",
            'business': f"https://source.unsplash.com/400x225/?business,office",
            'abstract': f"https://source.unsplash.com/400x225/?abstract,pattern"
        }
        
        url = thumbnail_options.get(category, f"https://source.unsplash.com/400x225/?{keywords}")
        
        try:
            response = requests.head(url, timeout=3)
            if response.status_code == 200:
                return url
        except:
            pass
        
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
        video_url = ""
        video_id = ""
        
        # Buscar todos os links
        all_links = element.find_all('a', href=True, recursive=True)
        if element.name == 'a' and element.get('href'):
            all_links.append(element)
        
        clip_links = []
        debug_links = [link.get('href') for link in all_links[:5]]
        
        # Priorizar links com /clip/
        for link in all_links:
            href = link.get('href', '')
            if '/clip/' in href or '/stock-footage/clip/' in href:
                clip_links.append(href)
        
        # Se não achou clips, pegar outros links
        if not clip_links:
            for link in all_links:
                href = link.get('href', '')
                if ('artlist.io' in href or href.startswith('/')) and '/artist/' not in href:
                    if any(pattern in href for pattern in ['/stock-footage/', '/video/', '/media/']):
                        clip_links.append(href)
        
        # Se ainda não achou, aceitar qualquer link longo
        if not clip_links:
            for link in all_links:
                href = link.get('href', '')
                if href and len(href) > 10:
                    clip_links.append(href)
        
        # Processar melhor link
        if clip_links:
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
            
            # Extrair ID da URL
            if video_url:
                numbers = re.findall(r'\d{4,}', video_url)
                if numbers:
                    video_id = numbers[-1]
                else:
                    all_numbers = re.findall(r'\d+', video_url)
                    if all_numbers:
                        video_id = all_numbers[-1]
        
        # Se não conseguiu ID da URL, usar atributos
        if not video_id:
            for attr in ['data-id', 'data-video-id', 'data-clip-id', 'id']:
                attr_value = element.get(attr)
                if attr_value:
                    numbers = re.findall(r'\d+', str(attr_value))
                    if numbers:
                        video_id = numbers[-1]
                        break
        
        # Último fallback para ID
        if not video_id:
            video_id = f"video_{index}_{int(time.time())}"
        
        # Buscar título
        title = ""
        
        # Primeiro: extrair da URL
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
        
        # Buscar thumbnail
        thumbnail_url = ""
        all_imgs = element.find_all('img')
        for img in all_imgs:
            src = (img.get('src') or 
                   img.get('data-src') or 
                   img.get('data-original') or
                   img.get('data-lazy') or "")
            if src:
                thumbnail_url = src
                break
        
        if thumbnail_url and thumbnail_url.startswith('/'):
            thumbnail_url = urljoin('https://artlist.io', thumbnail_url)
        
        if not thumbnail_url:
            thumbnail_url = generate_smart_thumbnail(title, video_url, video_id)
        
        result = {
            'ID': str(video_id),
            'Source': 'artlist.io',
            'Title': title,
            'Description': f"Links encontrados: {len(all_links)}, Clip links: {len(clip_links)}",
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': 'en'
        }
        
        if index == 0:
            debug_info = {
                'all_links_found': debug_links,
                'clip_links': clip_links[:3],
                'selected_url': video_url,
                'extracted_id': video_id,
                'title_source': 'URL' if video_url and title else 'HTML'
            }
            st.info("🔍 **Debug do primeiro elemento:**")
            st.json(debug_info)
        
        return result
        
    except Exception as e:
        st.error(f"Erro ao extrair elemento {index}: {e}")
        return None

def extract_with_requests(url, max_videos=20):
    """Extração usando requests + BeautifulSoup - VERSÃO SIMPLIFICADA E GARANTIDA"""
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
        
        with st.expander("🔧 Debug - HTML (primeiros 2000 chars)"):
            st.text(response.text[:2000])
        
        # BUSCAR APENAS URLs - método mais confiável
        clip_urls_in_html = re.findall(r'href="([^"]*(?:/clip/|/stock-footage/clip/)[^"]*)"', response.text)
        st.info(f"🔍 URLs de clip encontradas: {len(clip_urls_in_html)}")
        
        if clip_urls_in_html:
            st.success("✅ Links de vídeo encontrados!")
            for i, url_found in enumerate(clip_urls_in_html[:3]):
                st.write(f"   {i+1}. {url_found}")
            
            # PROCESSAR CADA URL ENCONTRADA
            for i, clip_url in enumerate(clip_urls_in_html[:max_videos]):
                
                # 1. CONSTRUIR URL COMPLETA
                if clip_url.startswith('/'):
                    full_url = f"https://artlist.io{clip_url}"
                else:
                    full_url = clip_url
                
                # 2. EXTRAIR ID - SEMPRE DO FINAL DA URL
                url_parts = full_url.rstrip('/').split('/')
                video_id = "unknown"
                
                # Pegar o último número da URL (método garantido)
                for part in reversed(url_parts):
                    if part.isdigit():
                        video_id = part
                        break
                
                # 3. EXTRAIR TÍTULO - DA PARTE ANTES DO ID
                title = "Untitled Video"
                for part in url_parts:
                    if part and not part.isdigit() and len(part) > 10 and '-' in part:
                        # Converter kebab-case para Title Case
                        title = part.replace('-', ' ').title()
                        break
                
                # 4. CRIAR DADOS DO VÍDEO
                video_data = {
                    'ID': video_id,
                    'Source': 'artlist.io',
                    'Title': title,
                    'Description': f"Video extracted from Artlist",
                    'Video URL': full_url,
                    'Thumbnail URL': generate_smart_thumbnail(title, full_url, video_id),
                    'Language': 'en'
                }
                
                df_data.append(video_data)
                st.success(f"✅ Vídeo {len(df_data)}: {title} (ID: {video_id})")
                
                # DEBUG do primeiro vídeo
                if len(df_data) == 1:
                    st.info("🔍 **Primeiro vídeo extraído:**")
                    st.info(f"   • URL original: {clip_url}")
                    st.info(f"   • URL completa: {full_url}")
                    st.info(f"   • ID extraído: {video_id}")
                    st.info(f"   • Título extraído: {title}")
            
            return df_data
        
        else:
            st.warning("⚠️ Nenhuma URL de clip encontrada no HTML")
            st.info("💡 Isso pode acontecer se o conteúdo for carregado via JavaScript")
            return []
        
    except Exception as e:
        st.error(f"Erro na extração: {e}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def main():
    st.markdown("### 🔧 Configurações")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        url_input = st.text_input(
            "URL do Artlist:",
            value="",
            placeholder="Cole aqui a URL do Artlist",
            help="URL da página de busca do Artlist"
        )
    
    with col2:
        max_videos = st.number_input(
            "Máx. vídeos:",
            min_value=1,
            max_value=50,
            value=20,
            help="Máximo de vídeos"
        )
    
    if st.button("🚀 Extrair Vídeos", type="primary"):
        if not url_input:
            st.error("⚠️ Insira uma URL válida do Artlist")
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
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total", len(df))
            with col2:
                st.metric("Com Título", len(df[df['Title'] != '']))
            with col3:
                st.metric("Com Thumbnail", len(df[df['Thumbnail URL'] != '']))
            
            st.dataframe(df, use_container_width=True)
            
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
                
                with col2:
                    st.json(sample)
        
        else:
            st.warning("❌ Nenhum vídeo encontrado")

with st.sidebar:
    st.header("ℹ️ Como usar")
    st.markdown("""
    1. Cole a URL do Artlist
    2. Defina quantos vídeos extrair
    3. Clique em "Extrair Vídeos"
    4. Baixe os dados em CSV/JSON
    """)

if __name__ == "__main__":
    main()
