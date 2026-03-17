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

# Lógica de extracción REFINADA
def extraer_datos_v2(texto, tipo):
    datos = {"numero": "", "fecha": "", "proveedor": ""}
    # Limpiamos líneas vacías y eliminamos ruidos comunes
    lineas = [l.strip() for l in texto.split('\n') if len(l.strip()) > 3]
    
    # 1. Extraer Proveedor (Buscamos la primera línea con sentido)
    ignore_list = ["+---", "NIT", "FECHA", "FACTURA", "PÁGINA", "PAGINA", "TEL", "DIRECCIÓN", "ELECTRONICA"]
    for l in lineas[:8]:
        if not any(x in l.upper() for x in ignore_list):
            datos["proveedor"] = l
            break

    # 2. Extraer Fecha
    match_fecha = re.search(r'(?:FECHA|EMISIÓN|GENERACIÓN|FECHA VALOR).*?(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})', texto, re.IGNORECASE | re.DOTALL)
    if match_fecha:
        datos["fecha"] = match_fecha.group(1)
    else:
        todas_fechas = re.findall(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', texto)
        if todas_fechas: datos["fecha"] = todas_fechas[0]

    # 3. Extraer Número
    if tipo == "Factura de Compra":
        match_num = re.search(r'(?:FACTURA|VENTA|ELECTRÓNICA).*?(?:NO\.|NRO|NUMERO)[:\s#]*([A-Z0-9-]+)', texto, re.IGNORECASE | re.DOTALL)
        if match_num:
            datos["numero"] = match_num.group(1)
    else:
        # Manifiestos/Declaraciones (Número largo)
        match_acep = re.search(r'(?:ACEPTACIÓN|DECLARACIÓN).*?[:\s#]*(\d{10,20})', texto, re.IGNORECASE | re.DOTALL)
        if match_acep:
            datos["numero"] = match_acep.group(1)

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
    ">📄 Ver PDF (Pág. {page_num})</button>
    """
    return js

# --- INTERFAZ ---
with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Operaciones", ["🔍 Buscador Rápido", "📤 Cargar Documentos"])
    st.divider()
    st.info("Sistema de Gestión de Documentación de Aduana.")

if choice == "📤 Cargar Documentos":
    st.header("Carga Masiva con Extracción")
    tipo_doc = st.radio("Tipo de archivos:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    
    # El uploader refresca la página al cambiar archivos
    archivos = st.file_uploader(f"Arrastre sus archivos PDF", type="pdf", accept_multiple_files=True)

    if archivos:
        # Usamos un botón para iniciar el análisis explícitamente y evitar duplicados de caché
        if st.button("🔍 Analizar Archivos"):
            st.session_state.pendientes = []
            
            with st.spinner("Leyendo documentos..."):
                for f in archivos:
                    f.seek(0) # Resetear puntero de lectura
                    pdf_bytes = f.read()
                    doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                    
                    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                        texto_meta = ""
                        # Analizamos las primeras 2 páginas para mayor contexto
                        for p in range(min(2, len(doc))):
                            texto_meta += doc[p].get_text()
                        
                        sugerencias = extraer_datos_v2(texto_meta, tipo_doc)
                        
                        st.session_state.pendientes.append({
                            "id": doc_id, "nombre": f.name, "tipo": tipo_doc,
                            "numero": sugerencias["numero"], "proveedor": sugerencias["proveedor"],
                            "fecha": sugerencias["fecha"], "blob": pdf_bytes
                        })

        # Mostrar tarjetas de revisión si hay pendientes
        if 'pendientes' in st.session_state and st.session_state.pendientes:
            st.subheader("📋 Revisión de datos")
            documentos_finales = []
            
            for i, d in enumerate(st.session_state.pendientes):
                with st.container():
                    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
                    st.write(f"📄 **{d['nombre']}**")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        new_num = st.text_input("Número", value=d['numero'], key=f"n_{d['id']}_{i}")
                    with c2:
                        new_prov = st.text_input("Proveedor", value=d['proveedor'], key=f"p_{d['id']}_{i}")
                    with c3:
                        new_fec = st.text_input("Fecha", value=d['fecha'], key=f"f_{d['id']}_{i}")
                    
                    documentos_finales.append({**d, "numero": new_num, "proveedor": new_prov, "fecha": new_fec})
                    st.markdown('</div>', unsafe_allow_html=True)

            if st.button("🚀 Guardar Todo en Base de Datos"):
                bar = st.progress(0)
                for idx, doc in enumerate(documentos_finales):
                    texto_full = ""
                    dict_pags = {}
                    with fitz.open(stream=doc['blob'], filetype="pdf") as pdf:
                        for p_idx, pagina in enumerate(pdf):
                            t = pagina.get_text().upper()
                            texto_full += t + " "
                            dict_pags[p_idx+1] = t
                    
                    try:
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)", 
                                 (doc['id'], doc['tipo'], doc['numero'], doc['fecha'], 
                                  doc['proveedor'].upper(), texto_full, doc['nombre'], 
                                  doc['blob'], json.dumps(dict_pags)))
                        conn.commit()
                    except sqlite3.IntegrityError:
                        pass
                    
                    bar.progress((idx + 1) / len(documentos_finales))
                
                st.success("✅ Guardado exitoso.")
                st.session_state.pendientes = []
                st.rerun()

elif choice == "🔍 Buscador Rápido":
    st.header("Buscador de Trazabilidad")
    query = st.text_input("Referencia a buscar").upper()

    if query:
        c.execute("SELECT id, tipo, numero, fecha, proveedor, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE contenido LIKE ?", (f'%{query}%',))
        res = c.fetchall()
        
        if res:
            st.write(f"Resultados: **{len(res)}**")
            for r in res:
                doc_id, tipo, num, fecha, prov, nombre, pags, blob = r
                with st.expander(f"📌 {tipo}: {num} - {prov}"):
                    encontrado = []
                    if pags:
                        p_dict = json.loads(pags)
                        encontrado = [p for p, cont in p_dict.items() if query in cont]
                    
                    col_i, col_b = st.columns([2, 1])
                    with col_i:
                        st.write(f"**Fecha:** {fecha} | **Archivo:** {nombre}")
                        if encontrado:
                            st.markdown(f'<div class="highlight-page">📍 Página(s): {", ".join(map(str, encontrado))}</div>', unsafe_allow_html=True)
                    
                    with col_b:
                        p_dest = encontrado[0] if encontrado else 1
                        st.components.v1.html(abrir_pdf_js(blob, p_dest), height=70)
                        st.download_button("💾 Bajar", blob, nombre, "application/pdf", key=f"d_{doc_id}")
        else:
            st.error("No se encontró la referencia.")
