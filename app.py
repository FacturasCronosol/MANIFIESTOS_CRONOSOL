import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64
import json

# Configuración profesional
st.set_page_config(page_title="Gestión Cronosol - DIAN", layout="wide", page_icon="🛡️")

# Estilo personalizado
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; background-color: #007bff; color: white; font-weight: bold; }
    .stDownloadButton>button { background-color: #28a745 !important; color: white !important; }
    .highlight-page { background-color: #fff3cd; padding: 5px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Inicialización de la base de datos
conn = sqlite3.connect('gestion_cronosol.db', check_same_thread=False)
c = conn.cursor()
# Añadimos la columna 'paginas_json' para guardar el texto por página
c.execute('''CREATE TABLE IF NOT EXISTS documentos 
             (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha TEXT, 
              proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB, paginas_json TEXT)''')
conn.commit()

def abrir_pdf_js(bin_file, page_num=1):
    base64_pdf = base64.b64encode(bin_file).decode('utf-8')
    # Script mejorado para abrir en una página específica si el visor del navegador lo soporta
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
        // Intentamos pasar el parámetro de página al visor nativo (#page=X)
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
    st.info("Sistema de localización de referencias por página para inspecciones DIAN.")

# --- MÓDULO DE CARGA ---
if choice == "📤 Cargar Documentos":
    st.header("Registro de Documentos con Indexación por Página")
    
    with st.form("form_carga", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tipo = st.selectbox("Documento", ["Factura de Compra", "Manifiesto de Aduana"])
            numero = st.text_input("Número del Documento")
        with col2:
            proveedor = st.text_input("Proveedor")
            fecha = st.date_input("Fecha")
            
        archivo = st.file_uploader("Subir PDF", type="pdf")
        submit = st.form_submit_button("Guardar y Analizar")

        if submit:
            if archivo and numero and proveedor:
                pdf_bytes = archivo.read()
                doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                
                c.execute("SELECT numero FROM documentos WHERE id=?", (doc_id,))
                if c.fetchone():
                    st.error("⚠️ Este documento ya existe.")
                else:
                    with st.spinner("Analizando páginas..."):
                        texto_completo = ""
                        dict_paginas = {}
                        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                            for i, pagina in enumerate(doc):
                                p_texto = pagina.get_text().upper()
                                texto_completo += p_texto + " "
                                dict_paginas[i+1] = p_texto # Guardamos texto por número de página
                        
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)", 
                                  (doc_id, tipo, numero, str(fecha), proveedor.upper(), 
                                   texto_completo, archivo.name, pdf_bytes, json.dumps(dict_paginas)))
                        conn.commit()
                        st.success(f"✅ Guardado. {len(dict_paginas)} páginas indexadas.")
            else:
                st.warning("Complete todos los campos.")

# --- MÓDULO DE BÚSQUEDA ---
elif choice == "🔍 Buscador Rápido":
    st.header("Localizador de Referencias")
    query = st.text_input("Referencia a buscar").upper()

    if query:
        # Buscamos documentos que contengan la palabra
        c.execute("SELECT id, tipo, numero, fecha, proveedor, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE contenido LIKE ?", (f'%{query}%',))
        resultados = c.fetchall()
        
        if resultados:
            st.write(f"Resultados para: `{query}`")
            for res in resultados:
                doc_id, tipo, num, fecha, prov, nombre, paginas_json, blob = res
                
                with st.expander(f"📌 {tipo}: {num} - {prov}"):
                    # Analizar en qué páginas está
                    paginas_dict = json.loads(paginas_json)
                    encontrado_en = [p for p, contenido in paginas_dict.items() if query in contenido]
                    
                    col_info, col_btn = st.columns([2, 1])
                    with col_info:
                        st.write(f"**Fecha:** {fecha}")
                        if encontrado_en:
                            st.markdown(f'<div class="highlight-page">📍 Encontrado en página(s): {", ".join(encontrado_en)}</div>', unsafe_allow_html=True)
                        else:
                            st.write("*(Referencia encontrada en metadatos o texto general)*")
                    
                    with col_btn:
                        # Si se encontró en una página específica, intentamos abrir esa por defecto
                        pag_destino = encontrado_en[0] if encontrado_en else 1
                        st.components.v1.html(abrir_pdf_js(blob, pag_destino), height=70)
                        
                        st.download_button(label="💾 Bajar PDF", data=blob, file_name=nombre, mime="application/pdf", key=f"dl_{doc_id}")
        else:
            st.error(f"No se encontró la referencia '{query}'.")
