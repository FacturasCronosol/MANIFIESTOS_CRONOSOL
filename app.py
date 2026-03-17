import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64
import json
import re
from datetime import datetime

# Configuración profesional
st.set_page_config(page_title="Gestión Cronosol - DIAN", layout="wide", page_icon="🛡️")

# Estilo personalizado
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; background-color: #007bff; color: white; font-weight: bold; }
    .stDownloadButton>button { background-color: #28a745 !important; color: white !important; }
    .highlight-page { background-color: #fff3cd; padding: 5px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# Inicialización de la base de datos
def init_db():
    conn = sqlite3.connect('gestion_cronosol.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documentos 
                 (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha TEXT, 
                  proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB, paginas_json TEXT)''')
    c.execute("PRAGMA table_info(documentos)")
    columnas = [col[1] for col in c.fetchall()]
    if 'paginas_json' not in columnas:
        c.execute("ALTER TABLE documentos ADD COLUMN paginas_json TEXT")
    conn.commit()
    return conn, c

conn, c = init_db()

# Extracción simplificada enfocada en FECHA con manejo de errores
def extraer_fecha_y_limpiar(texto):
    try:
        # Buscar fecha (DD/MM/AAAA o AAAA/MM/DD)
        match_fecha = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})', texto)
        if match_fecha:
            return match_fecha.group(1)
    except Exception:
        pass
    
    # Si falla o no encuentra, devuelve la fecha de hoy por defecto
    return datetime.now().strftime("%d/%m/%Y")

def abrir_pdf_js(bin_file, page_num=1):
    base64_pdf = base64.b64encode(bin_file).decode('utf-8')
    js = f"""
    <script>
    function openPDF() {{
        const byteCharacters = atob("{base64_pdf}");
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {{
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }}
        const byteArray = new Uint8Array(byteNumbers);
        const file = new Blob([byteArray], {{type: 'application/pdf'}});
        const fileURL = URL.createObjectURL(file);
        window.open(fileURL + '#page={page_num}', '_blank');
    }}
    </script>
    <button onclick="openPDF()" style="
        width: 100%; padding: 0.75em 1.5em; background-color: #28a745; color: white;
        border: none; border-radius: 8px; font-weight: bold; cursor: pointer;
    ">📄 Ver PDF (Pág. {page_num})</button>
    """
    return js

# --- INTERFAZ ---
with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Operaciones", ["🔍 Buscador Rápido", "📤 Cargar Documentos"])
    st.divider()
    st.info("Sistema de Auditoría y Trazabilidad DIAN.")

if choice == "📤 Cargar Documentos":
    st.header("Carga Masiva de Documentos")
    tipo_doc = st.radio("Tipo de archivos:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    
    archivos = st.file_uploader(f"Seleccione o arrastre archivos PDF", type="pdf", accept_multiple_files=True)

    if archivos:
        if st.button("⚡ Analizar y Preparar Carga"):
            st.session_state.pendientes = []
            
            with st.spinner("Analizando documentos..."):
                for f in archivos:
                    try:
                        f.seek(0)
                        pdf_bytes = f.read()
                        doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                        
                        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                            if len(doc) > 0:
                                texto_meta = doc[0].get_text()
                                fecha_sug = extraer_fecha_y_limpiar(texto_meta)
                                
                                # Nombre del archivo limpio
                                nombre_base = f.name.replace(".pdf", "").replace(".PDF", "")
                                
                                st.session_state.pendientes.append({
                                    "id": doc_id, 
                                    "nombre": f.name, 
                                    "tipo": tipo_doc,
                                    "numero": nombre_base,
                                    "proveedor": "POR DEFINIR", 
                                    "fecha": fecha_sug, 
                                    "blob": pdf_bytes
                                })
                    except Exception as e:
                        st.error(f"Error procesando {f.name}: {e}")

        if 'pendientes' in st.session_state and st.session_state.pendientes:
            st.subheader("📋 Verificación de Datos")
            st.info("El sistema ha pre-llenado los datos. Ajuste si es necesario antes de guardar.")
            
            documentos_finales = []
            for i, d in enumerate(st.session_state.pendientes):
                with st.container():
                    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
                    c1, c2, c3 = st.columns([3, 2, 2])
                    with c1:
                        st.markdown(f"📄 **Archivo:** {d['nombre']}")
                        new_prov = st.text_input("Proveedor", value=d['proveedor'], key=f"p_{d['id']}_{i}")
                    with c2:
                        new_num = st.text_input("No. Documento", value=d['numero'], key=f"n_{d['id']}_{i}")
                    with c3:
                        new_fec = st.text_input("Fecha", value=d['fecha'], key=f"f_{d['id']}_{i}")
                    
                    documentos_finales.append({**d, "numero": new_num, "proveedor": new_prov, "fecha": new_fec})
                    st.markdown('</div>', unsafe_allow_html=True)

            if st.button("🚀 Guardar Todo"):
                bar = st.progress(0)
                exitosos = 0
                for idx, doc in enumerate(documentos_finales):
                    texto_full = ""
                    dict_pags = {}
                    try:
                        with fitz.open(stream=doc['blob'], filetype="pdf") as pdf:
                            for p_idx, pagina in enumerate(pdf):
                                t = pagina.get_text().upper()
                                texto_full += t + " "
                                dict_pags[p_idx+1] = t
                        
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)", 
                                 (doc['id'], doc['tipo'], doc['numero'], doc['fecha'], 
                                  doc['proveedor'].upper(), texto_full, doc['nombre'], 
                                  doc['blob'], json.dumps(dict_pags)))
                        conn.commit()
                        exitosos += 1
                    except sqlite3.IntegrityError:
                        pass # Ya existe
                    except Exception as e:
                        st.error(f"Error al guardar {doc['nombre']}: {e}")
                    
                    bar.progress((idx + 1) / len(documentos_finales))
                
                st.success(f"✅ Se han indexado {exitosos} documentos correctamente.")
                st.session_state.pendientes = []
                st.rerun()

elif choice == "🔍 Buscador Rápido":
    st.header("Buscador de Referencias")
    query = st.text_input("Referencia, Factura o Manifiesto").upper()

    if query:
        c.execute("SELECT id, tipo, numero, fecha, proveedor, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE contenido LIKE ?", (f'%{query}%',))
        res = c.fetchall()
        
        if res:
            st.write(f"Coincidencias: **{len(res)}**")
            for r in res:
                doc_id, tipo, num, fecha, prov, nombre, pags, blob = r
                with st.expander(f"📅 {fecha} | {tipo}: {num} ({prov})"):
                    encontrado = []
                    if pags:
                        p_dict = json.loads(pags)
                        encontrado = [p for p, cont in p_dict.items() if query in cont]
                    
                    col_i, col_b = st.columns([2, 1])
                    with col_i:
                        st.write(f"Archivo: `{nombre}`")
                        if encontrado:
                            st.markdown(f'<div class="highlight-page">📍 Ubicado en página(s): {", ".join(map(str, encontrado))}</div>', unsafe_allow_html=True)
                    
                    with col_b:
                        p_dest = encontrado[0] if encontrado else 1
                        st.components.v1.html(abrir_pdf_js(blob, p_dest), height=70)
                        st.download_button("💾 Bajar PDF", blob, nombre, "application/pdf", key=f"d_{doc_id}")
        else:
            st.error("No se encontraron resultados.")
