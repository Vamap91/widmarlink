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
        
        # VERIFICAR se a página carrega vídeos via JavaScript
        if 'window.__INITIAL_STATE__' in response.text or 'window.__NEXT_DATA__' in response.text or '"videos"' in response.text:
            st.info("🔄 Página usa carregamento JavaScript - tentando extrair dados...")
            
            # Buscar dados JSON embedados na página
            js_data_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.__NEXT_DATA__\s*=\s*({.+?});',
                r'"videos"\s*:\s*(\[.+?\])',
                r'"clips"\s*:\s*(\[.+?\])',
                r'initialProps"\s*:\s*({.+?})'
            ]
            
            extracted_data = []
            for pattern in js_data_patterns:
                try:
                    matches = re.findall(pattern, response.text, re.DOTALL)
                    for match in matches:
                        try:
                            data = json.loads(match)
                            extracted_data.append(data)
                            st.success(f"✅ Dados JSON encontrados! Tipo: {type(data)}")
                        except:
                            continue
                except:
                    continue
            
            # Processar dados JSON encontrados
            if extracted_data:
                return process_json_data(extracted_data, max_videos)
        
        else:
            st.warning("⚠️ Página parece estática - processando HTML...")
        
        # CONTINUAR com método original se não encontrou JSON
        
        # BUSCAR URLs de clips na página de grade - MÚLTIPLOS PADRÕES
        clip_urls_patterns = [
            r'href="([^"]*(?:/clip/|/stock-footage/clip/)[^"]*)"',  # Links diretos
            r'["\']([^"\']*(?:/clip/|/stock-footage/clip/)[^"\']*)["\']',  # JavaScript
            r'to="([^"]*(?:/clip/|/stock-footage/clip/)[^"]*)"',  # Router links
            r'pathname["\s]*:["\s]*["\']([^"\']*(?:/clip/|/stock-footage/clip/)[^"\']*)["\']'  # Pathname configs
        ]
        
        clip_urls_in_html = []
        for pattern in clip_urls_patterns:
            urls = re.findall(pattern, response.text)
            clip_urls_in_html.extend(urls)
        
        # BUSCAR por IDs de vídeo em diferentes formatos
        video_ids_patterns = [
            r'data-(?:video-)?id["\s]*=["\']\s*(\d{6,8})["\']',  # data-id
            r'"id"\s*:\s*["\']?(\d{6,8})["\']?',  # JSON id
            r'videoId["\s]*:["\s]*["\']?(\d{6,8})["\']?',  # videoId
            r'clipId["\s]*:["\s]*["\']?(\d{6,8})["\']?',  # clipId
            r'/(\d{6,8})(?:["\s/]|$)'  # Números de 6-8 dígitos em URLs
        ]
        
        video_ids_in_html = []
        for pattern in video_ids_patterns:
            ids = re.findall(pattern, response.text)
            video_ids_in_html.extend(ids)
        
        # Remover duplicatas e limpar
        clip_urls_in_html = list(set([url for url in clip_urls_in_html if url and len(url) > 5]))
        video_ids_in_html = list(set([vid for vid in video_ids_in_html if vid and len(vid) >= 6]))
        
        st.info(f"🔍 URLs de clips encontradas: {len(clip_urls_in_html)}")
        st.info(f"🆔 IDs de vídeo encontrados: {len(video_ids_in_html)}")
        
        # BUSCAR DADOS DE IMAGENS/VÍDEOS na grade
        # Padrões mais amplos para páginas iniciais
        img_data = []
        
        # Buscar tags img com dados relevantes
        img_elements = soup.find_all('img')
        for img in img_elements:
            src = img.get('src', '')
            alt = img.get('alt', '')
            data_id = img.get('data-id', '') or img.get('id', '')
            
            # Filtrar apenas imagens que parecem ser de vídeos
            if (src and ('artlist' in src.lower() or src.startswith('/')) and 
                (alt or data_id or 'video' in src.lower() or 'clip' in src.lower())):
                img_data.append({
                    'alt': alt,
                    'src': src,
                    'id': data_id,
                    'parent_classes': ' '.join(img.parent.get('class', []) if img.parent else [])
                })
        
        st.info(f"🖼️ Imagens relevantes encontradas: {len(img_data)}")
        
        # DEBUG: Mostrar alguns dados encontrados
        if clip_urls_in_html:
            st.success("✅ URLs encontradas!")
            for i, url in enumerate(clip_urls_in_html[:3]):
                st.write(f"   {i+1}. {url}")
        
        if video_ids_in_html:
            st.success("✅ IDs encontrados!")
            for i, vid_id in enumerate(video_ids_in_html[:5]):
                st.write(f"   {i+1}. ID: {vid_id}")
        
        if img_data:
            st.success("✅ Dados de imagem encontrados!")
            for i, img in enumerate(img_data[:3]):
                st.write(f"   {i+1}. Alt: '{img['alt'][:30]}...', Src: {img['src'][:50]}...")
        
        # PROCESSAR VÍDEOS DA GRADE - PRIORIDADE POR MÉTODO
        processed_videos = []
        
        # Método 1: Se encontrou URLs de clips
        if clip_urls_in_html:
            st.info("🎯 Processando vídeos através das URLs...")
            
            for i, clip_url in enumerate(clip_urls_in_html[:max_videos]):
                video_data = process_video_from_url(clip_url, i, response.text)
                if video_data:
                    processed_videos.append(video_data)
        
        # Método 2: Se não encontrou URLs mas tem IDs, construir URLs
        elif video_ids_in_html:
            st.info("🎯 Construindo URLs a partir dos IDs encontrados...")
            
            for i, video_id in enumerate(video_ids_in_html[:max_videos]):
                # Tentar encontrar título correspondente nas imagens
                title = f"Artlist Video {video_id}"
                thumbnail = ""
                
                for img in img_data:
                    if video_id in img.get('id', '') or video_id in img.get('src', ''):
                        if img.get('alt'):
                            title = img['alt']
                        thumbnail = img['src']
                        break
                
                # Construir URL baseada no padrão do Artlist
                constructed_url = f"https://artlist.io/stock-footage/clip/video-{video_id}/{video_id}"
                
                video_data = {
                    'ID': video_id,
                    'Source': 'artlist.io',
                    'Title': title,
                    'Description': f"Video from Artlist grid - ID: {video_id}",
                    'Video URL': constructed_url,
                    'Thumbnail URL': thumbnail if thumbnail else generate_smart_thumbnail(title, constructed_url, video_id),
                    'Language': 'en'
                }
                
                processed_videos.append(video_data)
                st.success(f"✅ Vídeo {len(processed_videos)}: {title} (ID: {video_id})")
        
        # Método 4: FALLBACK AGRESSIVO - buscar qualquer coisa que pareça vídeo
        else:
            st.warning("⚠️ Usando método de fallback - busca agressiva...")
            
            # Buscar por qualquer número que possa ser ID de vídeo
            all_numbers = re.findall(r'\b(\d{6,8})\b', response.text)
            potential_ids = list(set(all_numbers))[:max_videos]
            
            st.info(f"🔢 Números encontrados que podem ser IDs: {len(potential_ids)}")
            
            if potential_ids:
                for i, potential_id in enumerate(potential_ids):
                    # Construir dados básicos
                    title = f"Artlist Video {potential_id}"
                    video_url = f"https://artlist.io/stock-footage/clip/video-{potential_id}/{potential_id}"
                    
                    # Tentar encontrar contexto para este ID
                    context_pattern = rf'.{{0,100}}{re.escape(potential_id)}.{{0,100}}'
                    context_matches = re.findall(context_pattern, response.text)
                    
                    if context_matches:
                        # Tentar extrair título do contexto
                        for context in context_matches:
                            title_match = re.search(r'"([^"]{10,60})"', context)
                            if title_match and 'http' not in title_match.group(1):
                                title = title_match.group(1)
                                break
                    
                    video_data = {
                        'ID': potential_id,
                        'Source': 'artlist.io',
                        'Title': title,
                        'Description': f"Video discovered via fallback method",
                        'Video URL': video_url,
                        'Thumbnail URL': generate_smart_thumbnail(title, video_url, potential_id),
                        'Language': 'en'
                    }
                    
                    processed_videos.append(video_data)
                    st.success(f"✅ Vídeo {len(processed_videos)}: {title} (ID: {potential_id})")
            
            else:
                st.error("❌ Nenhum padrão de vídeo encontrado na página")
                st.info("💡 Tente com uma URL específica de busca do Artlist")
        
        return processed_videos
        
    except Exception as e:
        st.error(f"Erro na extração: {e}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return []

def process_video_from_url(clip_url, index, html_content):
    """Processa um vídeo individual a partir da URL"""
    try:
        # Construir URL completa
        if clip_url.startswith('/'):
            full_url = f"https://artlist.io{clip_url}"
        else:
            full_url = clip_url
        
        # Extrair ID do final da URL
        url_parts = full_url.rstrip('/').split('/')
        video_id = "unknown"
        
        for part in reversed(url_parts):
            if part.isdigit():
                video_id = part
                break
        
        # Extrair título da URL
        title = "Untitled Video"
        for part in url_parts:
            if part and not part.isdigit() and len(part) > 8 and '-' in part:
                title = part.replace('-', ' ').title()
                break
        
        # Tentar encontrar título mais específico no HTML
        # Buscar por padrões próximos ao ID do vídeo
        title_patterns = [
            rf'"{video_id}"[^{{}}]*"title"\s*:\s*"([^"]+)"',
            rf'"title"\s*:\s*"([^"]*{video_id}[^"]*)"',
            rf'alt="([^"]*)"[^>]*(?:src="[^"]*{video_id}|data-id="{video_id}")'
        ]
        
        for pattern in title_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                potential_title = matches[0].strip()
                if len(potential_title) > len(title) and len(potential_title) < 100:
                    title = potential_title
                break
        
        video_data = {
            'ID': video_id,
            'Source': 'artlist.io',
            'Title': title,
            'Description': f"Video from Artlist grid",
            'Video URL': full_url,
            'Thumbnail URL': generate_smart_thumbnail(title, full_url, video_id),
            'Language': 'en'
        }
        
        if index == 0:
            st.info("🔍 **Primeiro vídeo da grade:**")
            st.info(f"   • URL: {full_url}")
            st.info(f"   • ID: {video_id}")
            st.info(f"   • Título: {title}")
        
        return video_data
        
    except Exception as e:
        st.warning(f"Erro ao processar vídeo {index}: {e}")
        return None

def process_json_data(json_data_list, max_videos):
    """Processa dados JSON extraídos da página"""
    processed_videos = []
    
    try:
        st.info("🎯 Processando dados JSON encontrados...")
        
        for data in json_data_list:
            videos_found = []
            
            # Buscar vídeos em diferentes estruturas JSON
            def find_videos_recursive(obj, path=""):
                if isinstance(obj, dict):
                    # Buscar chaves que podem conter vídeos
                    for key, value in obj.items():
                        if key.lower() in ['videos', 'clips', 'items', 'results', 'data']:
                            if isinstance(value, list):
                                videos_found.extend(value)
                        else:
                            find_videos_recursive(value, f"{path}.{key}")
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        find_videos_recursive(item, f"{path}[{i}]")
            
            find_videos_recursive(data)
            
            st.info(f"📹 Encontrados {len(videos_found)} itens de vídeo no JSON")
            
            # Processar cada vídeo encontrado
            for i, video_item in enumerate(videos_found[:max_videos]):
                if len(processed_videos) >= max_videos:
                    break
                
                try:
                    # Extrair dados do objeto vídeo
                    video_data = extract_video_from_json(video_item, i)
                    if video_data:
                        processed_videos.append(video_data)
                        st.success(f"✅ Vídeo JSON {len(processed_videos)}: {video_data.get('Title', 'Sem título')}")
                except Exception as e:
                    st.warning(f"Erro ao processar vídeo JSON {i}: {e}")
                    continue
        
        return processed_videos
        
    except Exception as e:
        st.error(f"Erro ao processar dados JSON: {e}")
        return []

def extract_video_from_json(video_obj, index):
    """Extrai dados de um objeto JSON de vídeo"""
    try:
        if not isinstance(video_obj, dict):
            return None
        
        # Buscar ID em diferentes campos
        video_id = (video_obj.get('id') or 
                   video_obj.get('videoId') or 
                   video_obj.get('clipId') or 
                   video_obj.get('_id') or
                   f"json_{index}")
        
        # Buscar título
        title = (video_obj.get('title') or 
                video_obj.get('name') or 
                video_obj.get('alt') or
                video_obj.get('description', '')[:50] or
                f"Artlist Video {video_id}")
        
        # Buscar URL do vídeo
        video_url = ""
        url_fields = ['url', 'videoUrl', 'clipUrl', 'link', 'permalink', 'slug']
        for field in url_fields:
            if video_obj.get(field):
                url = video_obj[field]
                if isinstance(url, str):
                    if url.startswith('/'):
                        video_url = f"https://artlist.io{url}"
                    elif 'artlist.io' in url:
                        video_url = url
                    elif url.startswith('http'):
                        video_url = url
                    break
        
        # Se não encontrou URL, construir baseada no ID
        if not video_url and video_id:
            slug = title.lower().replace(' ', '-').replace(',', '')[:50]
            video_url = f"https://artlist.io/stock-footage/clip/{slug}/{video_id}"
        
        # Buscar thumbnail
        thumbnail_url = ""
        thumb_fields = ['thumbnail', 'thumbnailUrl', 'image', 'poster', 'preview']
        for field in thumb_fields:
            if video_obj.get(field):
                thumb = video_obj[field]
                if isinstance(thumb, str):
                    if thumb.startswith('/'):
                        thumbnail_url = f"https://artlist.io{thumb}"
                    elif thumb.startswith('http'):
                        thumbnail_url = thumb
                    break
        
        # Se não encontrou thumbnail, gerar uma
        if not thumbnail_url:
            thumbnail_url = generate_smart_thumbnail(title, video_url, video_id)
        
        # Buscar descrição
        description = (video_obj.get('description') or 
                      video_obj.get('summary') or
                      f"Video extracted from JSON data")
        
        video_data = {
            'ID': str(video_id),
            'Source': 'artlist.io',
            'Title': title,
            'Description': description[:200],  # Limitar tamanho
            'Video URL': video_url,
            'Thumbnail URL': thumbnail_url,
            'Language': 'en'
        }
        
        return video_data
        
    except Exception as e:
        st.warning(f"Erro ao extrair vídeo do JSON: {e}")
        return None

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
