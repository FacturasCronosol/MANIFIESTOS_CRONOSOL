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
    
    .highlight-page { background-color: #fff3cd; padding: 10px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; color: #856404; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; }
    
    /* Estilo para los botones de descarga de inventario */
    .stDownloadButton>button { background-color: #007bff !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- UTILIDADES ---

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

def generar_zip_blob(lista_resultados, usar_resaltado=False, queries=[]):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for r in lista_resultados:
            # Estructura r: (id, tipo, num, fecha, proveedor, contenido, nombre, blob, pags)
            # Dependiendo de la query SQL la posición varía, usamos índices calculados
            nombre = r[6] if r[6].lower().endswith(".pdf") else f"{r[6]}.pdf"
            blob = r[7]
            if usar_resaltado and queries:
                blob = resaltar_pdf_multiple(blob, queries)
            zf.writestr(nombre, blob)
    return buf.getvalue()

# --- COMPONENTES ---

def render_editor_documento(r, search_terms=[]):
    # Estructura r: (id, tipo, num, fecha, proveedor, contenido, nombre, blob, pags)
    doc_id, tipo, num, fecha_iso, proveedor, contenido, nombre, blob, pags = r
    t1, t2 = st.tabs(["📄 Ver / Resultados", "⚙️ Gestionar Datos"])
    
    with t1:
        p_dict = json.loads(pags)
        p_encontradas = []
        if search_terms:
            for p, cont in p_dict.items():
                if any(q.upper() in cont.upper() for q in search_terms):
                    p_encontradas.append(int(p))
        
        if p_encontradas:
            st.markdown(f'<div class="highlight-page">📍 Términos encontrados en pág: {", ".join(map(str, sorted(p_encontradas)))}</div>', unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        p_ini = min(p_encontradas) if p_encontradas else 1
        
        with c1:
            pdf_resaltado = resaltar_pdf_multiple(blob, search_terms)
            st.components.v1.html(abrir_pdf_js(pdf_resaltado, p_ini, f"res_{doc_id}", f"Ver PDF Resaltado (Pág. {p_ini})", "#28a745"), height=65)
        
        with c2:
            st.components.v1.html(abrir_pdf_js(blob, p_ini, f"orig_{doc_id}", "Ver PDF Original", "#6c757d"), height=65)

    with t2:
        col_ed1, col_ed2 = st.columns(2)
        new_tipo = col_ed1.selectbox("Tipo", ["Factura de Compra", "Manifiesto de Aduana"], index=0 if "Factura" in tipo else 1, key=f"edit_t_{doc_id}")
        
        # Selector de fecha real
        try:
            curr_date = datetime.strptime(fecha_iso, "%Y-%m-%d")
        except:
            curr_date = datetime.now()
        new_fecha_dt = col_ed2.date_input("Fecha", value=curr_date, key=f"edit_f_{doc_id}")
        new_fecha = new_fecha_dt.strftime("%Y-%m-%d")
        
        col_ed3, col_ed4 = st.columns(2)
        new_num = col_ed3.text_input("Número de Documento", value=num, key=f"edit_n_{doc_id}")
        new_prov = col_ed4.text_input("Proveedor", value=proveedor, key=f"edit_p_{doc_id}")
        
        st.divider()
        col_btn1, col_btn2 = st.columns([1, 1])
        if col_btn1.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
            c.execute("UPDATE documentos SET tipo=?, fecha_iso=?, numero=?, proveedor=? WHERE id=?", 
                     (new_tipo, new_fecha, new_num, new_prov, doc_id))
            conn.commit()
            st.success("Cambios guardados correctamente")
            st.rerun()
        if col_btn2.button("🗑️ Eliminar Documento", key=f"del_{doc_id}"):
            c.execute("DELETE FROM documentos WHERE id=?", (doc_id,))
            conn.commit()
            st.rerun()

# --- APP ---

with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Navegación", ["🔍 Buscador", "📂 Inventario", "📤 Carga"])

if choice == "🔍 Buscador":
    st.header("Buscador Inteligente")
    query_input = st.text_input("Referencias o palabras clave (separe por coma)").upper()
    
    if query_input:
        queries = [q.strip() for q in query_input.split(",") if q.strip()]
        sql_cond = " OR ".join(["contenido LIKE ?" for _ in queries])
        params = [f"%{q}%" for q in queries]
        
        # Obtenemos todos los campos para el editor
        c.execute(f"SELECT id, tipo, numero, fecha_iso, proveedor, contenido, nombre_archivo, pdf_blob, paginas_json FROM documentos WHERE {sql_cond} ORDER BY fecha_iso DESC", params)
        resultados = c.fetchall()
        
        if resultados:
            st.subheader(f"Resultados encontrados: {len(resultados)}")
            
            st.write("📂 **Acciones Masivas para esta búsqueda:**")
            cz1, cz2 = st.columns(2)
            
            with cz1:
                zip_resaltado = generar_zip_blob(resultados, True, queries)
                st.download_button("📥 Descargar Resultados Subrayados (.zip)", zip_resaltado, "busqueda_resaltada.zip", "application/zip", key="dl_zip_res")
            
            with cz2:
                zip_original = generar_zip_blob(resultados, False)
                st.download_button("📥 Descargar Resultados Originales (.zip)", zip_original, "busqueda_original.zip", "application/zip", key="dl_zip_orig")
            
            st.divider()
            
            for r in resultados:
                # r[5] es el contenido para el expander
                coincide = [q for q in queries if q in r[5]]
                with st.expander(f"📄 {r[3]} | {r[6]} ({', '.join(coincide)})"):
                    render_editor_documento(r, queries)
        else:
            st.warning("No se encontraron coincidencias para los términos ingresados.")

elif choice == "📂 Inventario":
    st.header("Archivo General")
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.subheader("📝 Facturas de Compra")
        c.execute("SELECT id, tipo, numero, fecha_iso, proveedor, contenido, nombre_archivo, pdf_blob, paginas_json FROM documentos WHERE tipo='Factura de Compra' ORDER BY fecha_iso DESC")
        facturas = c.fetchall()
        if facturas:
            zip_f = generar_zip_blob(facturas)
            st.download_button(f"📥 Descargar {len(facturas)} Facturas (.zip)", zip_f, "todas_las_facturas.zip", key="btn_all_f")
            for f in facturas:
                with st.expander(f"📅 {f[3]} | {f[6]}"):
                    render_editor_documento(f)
        else: st.info("No hay facturas cargadas.")

    with col_f2:
        st.subheader("🚢 Manifiestos de Aduana")
        c.execute("SELECT id, tipo, numero, fecha_iso, proveedor, contenido, nombre_archivo, pdf_blob, paginas_json FROM documentos WHERE tipo='Manifiesto de Aduana' ORDER BY fecha_iso DESC")
        manifiestos = c.fetchall()
        if manifiestos:
            zip_m = generar_zip_blob(manifiestos)
            st.download_button(f"📥 Descargar {len(manifiestos)} Manifiestos (.zip)", zip_m, "todos_los_manifiestos.zip", key="btn_all_m")
            for m in manifiestos:
                with st.expander(f"📅 {m[3]} | {m[6]}"):
                    render_editor_documento(m)
        else: st.info("No hay manifiestos cargados.")

elif choice == "📤 Carga":
    st.header("Carga Masiva de Documentos")
    t_doc = st.radio("Tipo de Documento:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    
    # Se añade el uploader
    f_up = st.file_uploader("Subir archivos PDF", type="pdf", accept_multiple_files=True)
    
    if f_up:
        st.info(f"Archivos listos para procesar: {len(f_up)}")
        # Solo se procesa si se hace clic en el botón
        if st.button("⚡ Analizar Documentos"):
            progress_bar = st.progress(0)
            for idx, f in enumerate(f_up):
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
                        # Intentamos insertar valores por defecto que luego se pueden editar
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)",
                                 (doc_id, t_doc, f.name, datetime.now().strftime("%Y-%m-%d"), "PENDIENTE", full_txt, f.name, b, json.dumps(p_map)))
                        conn.commit()
                    except sqlite3.IntegrityError:
                        pass # Ya existe el documento
                progress_bar.progress((idx + 1) / len(f_up))
            st.success("Procesamiento completado. Los documentos ya están en el sistema.")
