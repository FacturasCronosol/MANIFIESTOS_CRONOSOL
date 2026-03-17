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
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 10px; background-color: #f9f9f9; }
    </style>
    """, unsafe_allow_html=True)

# Inicialización de la base de datos con migración automática
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

# Lógica de extracción automática (Afinada para documentos DIAN/Facturas)
def extraer_datos_basicos(texto, tipo):
    datos = {"numero": "", "fecha": "", "proveedor": ""}
    
    # Intento de extraer fecha (formatos comunes)
    fechas = re.findall(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', texto)
    if fechas: datos["fecha"] = fechas[0]
    
    if tipo == "Factura de Compra":
        # Busca patrones como "Factura de Venta No. XXX" o "FE-XXX"
        nums = re.findall(r'(?:FACTURA|NÚMERO|NO\.)\s*[:#-]?\s*([A-Z0-9-]+)', texto)
        if nums: datos["numero"] = nums[0]
    else:
        # Busca "Número de Aceptación" en manifiestos
        nums = re.findall(r'(?:ACEPTACIÓN|DECLARACIÓN)\s*(?:NO\.)?\s*[:#-]?\s*(\d{10,})', texto)
        if nums: datos["numero"] = nums[0]
        
    # El proveedor suele ser de las primeras líneas o estar cerca del NIT
    lineas = [l.strip() for l in texto.split('\n') if len(l.strip()) > 3]
    if lineas: datos["proveedor"] = lineas[0][:50] # Toma la primera línea coherente
    
    return datos

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
    ">📄 Visualizar PDF (Página {page_num})</button>
    """
    return js

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Operaciones", ["🔍 Buscador Rápido", "📤 Cargar Documentos"])
    st.divider()
    st.info("Utilice el buscador para localizar referencias en facturas y manifiestos de aduana.")

# --- MÓDULO DE CARGA ---
if choice == "📤 Cargar Documentos":
    st.header("Estación de Carga Masiva e Inteligente")
    
    tipo_doc = st.radio("Seleccione el tipo de documentos que va a cargar:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    archivos = st.file_uploader(f"Arrastre aquí sus {tipo_doc} (Múltiples permitidos)", type="pdf", accept_multiple_files=True)

    if archivos:
        st.subheader("⚙️ Procesando archivos...")
        
        # Lista para manejar los datos antes de confirmar
        if 'pendientes' not in st.session_state:
            st.session_state.pendientes = []

        for f in archivos:
            # Evitar procesar el mismo archivo dos veces en la misma sesión
            if not any(d['nombre'] == f.name for d in st.session_state.pendientes):
                pdf_bytes = f.read()
                doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                
                # Análisis rápido de la primera página para sugerir datos
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    texto_primera_pag = doc[0].get_text().upper()
                    sugerencias = extraer_datos_basicos(texto_primera_pag, tipo_doc)
                    
                    st.session_state.pendientes.append({
                        "id": doc_id,
                        "nombre": f.name,
                        "tipo": tipo_doc,
                        "numero": sugerencias["numero"],
                        "proveedor": sugerencias["proveedor"],
                        "fecha": sugerencias["fecha"],
                        "blob": pdf_bytes
                    })

        # Tabla de revisión
        st.info("Revise y complete los datos detectados antes de guardar en la base de datos definitiva.")
        
        documentos_listos = []
        for i, doc_p in enumerate(st.session_state.pendientes):
            with st.container():
                st.markdown(f'<div class="upload-card">', unsafe_allow_html=True)
                col_n, col_num, col_prov, col_fec = st.columns([2, 2, 3, 2])
                with col_n:
                    st.text(f"📄 {doc_p['nombre'][:25]}...")
                with col_num:
                    num_val = st.text_input("Número", value=doc_p["numero"], key=f"num_{i}")
                with col_prov:
                    prov_val = st.text_input("Proveedor", value=doc_p["proveedor"], key=f"prov_{i}")
                with col_fec:
                    fec_val = st.text_input("Fecha", value=doc_p["fecha"], key=f"fec_{i}")
                
                documentos_listos.append({
                    **doc_p, "numero": num_val, "proveedor": prov_val, "fecha": fec_val
                })
                st.markdown('</div>', unsafe_allow_html=True)

        if st.button("🚀 Guardar e Indexar Todo"):
            progreso = st.progress(0)
            status_text = st.empty()
            
            for index, doc_f in enumerate(documentos_listos):
                status_text.text(f"Analizando {doc_f['nombre']}...")
                
                # Indexación completa por página
                texto_completo = ""
                dict_paginas = {}
                with fitz.open(stream=doc_f['blob'], filetype="pdf") as pdf:
                    total_pags = len(pdf)
                    for i, pagina in enumerate(pdf):
                        p_texto = pagina.get_text().upper()
                        texto_completo += p_texto + " "
                        dict_paginas[i+1] = p_texto
                
                try:
                    c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)", 
                              (doc_f['id'], doc_f['tipo'], doc_f['numero'], doc_f['fecha'], 
                               doc_f['proveedor'].upper(), texto_completo, doc_f['nombre'], 
                               doc_f['blob'], json.dumps(dict_paginas)))
                    conn.commit()
                except sqlite3.IntegrityError:
                    st.warning(f"⚠️ El archivo {doc_f['nombre']} ya estaba en la base de datos.")
                
                progreso.progress((index + 1) / len(documentos_listos))
            
            st.success("✅ ¡Proceso completado! Todos los documentos han sido indexados.")
            st.session_state.pendientes = [] # Limpiar lista
            st.balloons()

# --- MÓDULO DE BÚSQUEDA ---
elif choice == "🔍 Buscador Rápido":
    st.header("Localizador de Referencias")
    query = st.text_input("Referencia a buscar").upper()

    if query:
        c.execute("SELECT id, tipo, numero, fecha, proveedor, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE contenido LIKE ?", (f'%{query}%',))
        resultados = c.fetchall()
        
        if resultados:
            st.write(f"Resultados para: `{query}`")
            for res in resultados:
                doc_id, tipo, num, fecha, prov, nombre, paginas_json, blob = res
                
                with st.expander(f"📌 {tipo}: {num} - {prov}"):
                    encontrado_en = []
                    if paginas_json:
                        paginas_dict = json.loads(paginas_json)
                        encontrado_en = [p for p, contenido in paginas_dict.items() if query in contenido]
                    
                    col_info, col_btn = st.columns([2, 1])
                    with col_info:
                        st.write(f"**Fecha:** {fecha}")
                        if encontrado_en:
                            st.markdown(f'<div class="highlight-page">📍 Encontrado en página(s): {", ".join(map(str, encontrado_en))}</div>', unsafe_allow_html=True)
                        else:
                            st.write("*(Referencia encontrada en texto general)*")
                    
                    with col_btn:
                        pag_destino = encontrado_en[0] if encontrado_en else 1
                        st.components.v1.html(abrir_pdf_js(blob, pag_destino), height=70)
                        st.download_button(label="💾 Bajar PDF", data=blob, file_name=nombre, mime="application/pdf", key=f"dl_{doc_id}")
        else:
            st.error(f"No se encontró la referencia '{query}'.")
