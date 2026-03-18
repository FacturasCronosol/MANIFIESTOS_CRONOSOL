import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64
import json
import re
import os
import zipfile
from io import BytesIO
from datetime import datetime

# Configuración profesional
st.set_page_config(
    page_title="Gestión Cronosol - DIAN", 
    layout="wide", 
    page_icon="🛡️"
)

# Estilo personalizado
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; }
    
    /* Botón Guardar */
    div[key*="save_"] button { background-color: #28a745 !important; color: white !important; }
    /* Botón Eliminar */
    div[key*="del_"] button { background-color: #dc3545 !important; color: white !important; }
    
    .highlight-page { background-color: #fff3cd; padding: 10px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; }
    
    /* Botones de descarga ZIP superiores */
    .zip-download-container {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        margin-bottom: 25px;
    }
    
    /* Botón PDF Original (Gris/Azul oscuro) */
    .btn-original button {
        background-color: #6c757d !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- UTILIDADES ---

MESES_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun", 7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

def init_db():
    conn = sqlite3.connect('gestion_cronosol_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documentos 
                 (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha_iso TEXT, 
                  proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB, paginas_json TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

def resaltar_pdf_multiple(pdf_bytes, queries):
    if not queries: return pdf_bytes
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            for q in queries:
                if q.strip():
                    for inst in page.search_for(q.strip()):
                        annot = page.add_highlight_annot(inst)
                        annot.update()
        output = doc.write()
        doc.close()
        return output
    except: return pdf_bytes

def abrir_pdf_js(bin_file, page_num=1, btn_id="", label="📄 Ver PDF", color="#28a745"):
    b64 = base64.b64encode(bin_file).decode('utf-8')
    return f"""
    <script>
    function open_{btn_id}() {{
        const bytes = atob("{b64}");
        const arr = new Uint8Array(bytes.length);
        for (let i=0; i<bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([arr], {{type: 'application/pdf'}}));
        window.open(url + '#page={page_num}', '_blank');
    }}
    </script>
    <button onclick="open_{btn_id}()" style="
        width: 100%; padding: 0.75em; background-color: {color}; color: white;
        border: none; border-radius: 8px; font-weight: bold; cursor: pointer;
    ">{label}</button>
    """

def generar_zip_busqueda(lista_resultados, usar_resaltado=False, queries=[]):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for r in lista_resultados:
            # id, tipo, numero, fecha, nombre, pags, blob...
            nombre = r[4] if r[4].lower().endswith(".pdf") else f"{r[4]}.pdf"
            blob = r[6]
            if usar_resaltado and queries:
                blob = resaltar_pdf_multiple(blob, queries)
            zf.writestr(nombre, blob)
    return buf.getvalue()

# --- COMPONENTES ---

def render_editor_documento(r, search_terms=[]):
    doc_id, tipo, num, fecha_iso, nombre, pags, blob = r
    t1, t2 = st.tabs(["📄 Visualización", "⚙️ Gestión"])
    
    with t1:
        p_dict = json.loads(pags)
        p_encontradas = []
        if search_terms:
            for p, cont in p_dict.items():
                if any(q.upper() in cont.upper() for q in search_terms):
                    p_encontradas.append(int(p))
        
        if p_encontradas:
            st.markdown(f'<div class="highlight-page">📍 Coincidencias en página(s): {", ".join(map(str, sorted(p_encontradas)))}</div>', unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        p_ini = min(p_encontradas) if p_encontradas else 1
        
        # Botón 1: Resaltado
        with c1:
            pdf_resaltado = resaltar_pdf_multiple(blob, search_terms)
            st.components.v1.html(abrir_pdf_js(pdf_resaltado, p_ini, f"res_{doc_id}", f"Ver PDF Resaltado (Pág. {p_ini})", "#28a745"), height=60)
        
        # Botón 2: Original
        with c2:
            st.components.v1.html(abrir_pdf_js(blob, p_ini, f"orig_{doc_id}", "Ver PDF Original", "#6c757d"), height=60)

    with t2:
        # Formulario de edición (simplificado para este ejemplo)
        new_nombre = st.text_input("Nombre", value=nombre, key=f"edit_n_{doc_id}")
        new_tipo = st.selectbox("Tipo", ["Factura de Compra", "Manifiesto de Aduana"], index=0 if "Factura" in tipo else 1, key=f"edit_t_{doc_id}")
        col_d1, col_d2 = st.columns(2)
        if col_d1.button("💾 Guardar", key=f"save_{doc_id}"):
            c.execute("UPDATE documentos SET nombre_archivo=?, tipo=? WHERE id=?", (new_nombre, new_tipo, doc_id))
            conn.commit()
            st.rerun()
        if col_d2.button("🗑️ Eliminar", key=f"del_{doc_id}"):
            c.execute("DELETE FROM documentos WHERE id=?", (doc_id,))
            conn.commit()
            st.rerun()

# --- APP ---

with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Navegación", ["🔍 Buscador", "📂 Inventario", "📤 Carga"])

if choice == "🔍 Buscador":
    st.header("Buscador Inteligente")
    query_input = st.text_input("Referencias (sepárelas por coma)").upper()
    
    if query_input:
        queries = [q.strip() for q in query_input.split(",") if q.strip()]
        sql_cond = " OR ".join(["contenido LIKE ?" for _ in queries])
        params = [f"%{q}%" for q in queries]
        
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob, contenido FROM documentos WHERE {sql_cond} ORDER BY fecha_iso DESC", params)
        resultados = c.fetchall()
        
        if resultados:
            st.markdown(f"### Resultados encontrados: {len(resultados)}")
            
            # --- SECCIÓN DE DESCARGA ZIP SUPERIOR ---
            with st.container():
                st.markdown('<div class="zip-download-container">', unsafe_allow_html=True)
                st.write("📂 **Acciones Masivas para esta búsqueda:**")
                cz1, cz2 = st.columns(2)
                
                zip_resaltado = generar_zip_busqueda(resultados, True, queries)
                cz1.download_button("📥 Descargar Todos Subrayados (.zip)", zip_resaltado, "busqueda_resaltada.zip", "application/zip")
                
                zip_original = generar_zip_busqueda(resultados, False)
                cz2.download_button("📥 Descargar Todos Originales (.zip)", zip_original, "busqueda_original.zip", "application/zip")
                st.markdown('</div>', unsafe_allow_html=True)
            
            for r in resultados:
                # Mostrar expander
                coincide = [q for q in queries if q in r[7]]
                with st.expander(f"📄 {r[3]} | {r[4]} ({', '.join(coincide)})"):
                    render_editor_documento(r[:7], queries)
        else:
            st.warning("No hay coincidencias.")

elif choice == "📂 Inventario":
    st.header("Archivo General")
    c.execute("SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos ORDER BY fecha_iso DESC")
    todos = c.fetchall()
    for r in todos:
        with st.expander(f"{r[3]} | {r[1]} - {r[4]}"):
            render_editor_documento(r)

elif choice == "📤 Carga":
    st.header("Carga Masiva")
    t_doc = st.radio("Tipo:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    f_up = st.file_uploader("PDFs", type="pdf", accept_multiple_files=True)
    if f_up and st.button("⚡ Procesar"):
        for f in f_up:
            b = f.read()
            doc_id = hashlib.sha256(b).hexdigest()
            with fitz.open(stream=b, filetype="pdf") as pdf:
                full_txt = ""
                p_map = {}
                for i, p in enumerate(pdf):
                    txt = p.get_text().upper()
                    full_txt += txt + " "
                    p_map[i+1] = txt
                try:
                    c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)",
                             (doc_id, t_doc, f.name, datetime.now().strftime("%Y-%m-%d"), "PROVEEDOR", full_txt, f.name, b, json.dumps(p_map)))
                    conn.commit()
                except: pass
        st.success("Cargado.")
