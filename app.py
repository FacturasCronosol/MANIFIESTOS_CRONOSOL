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

# Configuración profesional de la página
st.set_page_config(
    page_title="Gestión Cronosol - DIAN", 
    layout="wide", 
    page_icon="🛡️"
)

# --- ESTILOS PERSONALIZADOS ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; }
    
    /* Botón Guardar (Verde) */
    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] .stButton button[key*="save_"] {
        background-color: #28a745 !important; color: white !important; border: none;
    }

    /* Botón Eliminar (Rojo) */
    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] .stButton button[key*="del_"] {
        background-color: #dc3545 !important; color: white !important; border: none;
    }
    
    .stDownloadButton>button { background-color: #007bff !important; color: white !important; }

    .highlight-page { background-color: #fff3cd; padding: 10px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; color: #856404; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    
    .zip-download-container {
        background-color: #f8f9fa;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        margin-bottom: 25px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTES Y BASE DE DATOS ---
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

# --- FUNCIONES DE PROCESAMIENTO ---

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

def extraer_fecha_texto(texto):
    texto_limpio = texto.upper()
    patrones = [r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', r'(\d{1,2}\s+[A-Z]{3,10}\s+\d{4})']
    for pat in patrones:
        match = re.search(pat, texto_limpio)
        if match:
            f = match.group(0)
            try:
                parts = re.split(r'[/-]', f)
                if len(parts[0]) == 4: return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                else: return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
            except: pass
    return datetime.now().strftime("%Y-%m-%d")

def generar_zip_blob(resultados, usar_resaltado=False, queries=[]):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for r in resultados:
            nombre = r[4] if r[4].lower().endswith(".pdf") else f"{r[4]}.pdf"
            blob = r[6]
            if usar_resaltado and queries:
                blob = resaltar_pdf_multiple(blob, queries)
            zf.writestr(nombre, blob)
    return buf.getvalue()

# --- INTERFAZ DE EDICIÓN ---

def render_editor_documento(r, search_terms=[]):
    doc_id, tipo, num, fecha_iso, nombre, pags, blob = r
    t1, t2 = st.tabs(["📄 Visualización", "⚙️ Gestión de Datos"])
    
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
        
        with c1:
            pdf_resaltado = resaltar_pdf_multiple(blob, search_terms)
            st.components.v1.html(abrir_pdf_js(pdf_resaltado, p_ini, f"res_{doc_id}", f"Ver PDF Resaltado (Pág. {p_ini})", "#28a745"), height=65)
        
        with c2:
            st.components.v1.html(abrir_pdf_js(blob, p_ini, f"orig_{doc_id}", "Ver PDF Original", "#6c757d"), height=65)

    with t2:
        edit_nombre = st.text_input("Nombre del archivo", value=nombre, key=f"edit_n_{doc_id}")
        col_ed1, col_ed2 = st.columns(2)
        edit_tipo = col_ed1.selectbox("Tipo de Documento", ["Factura de Compra", "Manifiesto de Aduana"], index=0 if "Factura" in tipo else 1, key=f"edit_t_{doc_id}")
        
        try: f_dt = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
        except: f_dt = datetime.now().date()
        edit_fecha = col_ed2.date_input("Fecha", value=f_dt, key=f"edit_f_{doc_id}")
        
        st.divider()
        cb1, cb2 = st.columns(2)
        
        if f"confirm_del_{doc_id}" not in st.session_state:
            if cb1.button("🗑️ Eliminar Documento", key=f"del_{doc_id}"):
                st.session_state[f"confirm_del_{doc_id}"] = True
                st.rerun()
        else:
            st.error("¿Confirmar eliminación definitiva?")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ Confirmar", key=f"c_ok_{doc_id}"):
                c.execute("DELETE FROM documentos WHERE id=?", (doc_id,))
                conn.commit()
                del st.session_state[f"confirm_del_{doc_id}"]
                st.rerun()
            if cc2.button("❌ Cancelar", key=f"c_no_{doc_id}"):
                del st.session_state[f"confirm_del_{doc_id}"]
                st.rerun()

        if cb2.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
            c.execute("UPDATE documentos SET tipo=?, nombre_archivo=?, fecha_iso=? WHERE id=?", 
                     (edit_tipo, edit_nombre, edit_fecha.strftime("%Y-%m-%d"), doc_id))
            conn.commit()
            st.success("¡Documento actualizado!")
            st.rerun()

# --- APLICACIÓN PRINCIPAL ---

if 'pendientes' not in st.session_state: st.session_state.pendientes = []
if 'uploader_id' not in st.session_state: st.session_state.uploader_id = 0

with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Menú Principal", ["🔍 Buscador", "📂 Documentos", "📤 Carga Masiva"])
    st.divider()
    st.info("Sistema de Trazabilidad Aduanera.")

if choice == "📤 Carga Masiva":
    st.header("Carga Masiva de Documentos")
    tipo_up = st.radio("Tipo de Documento:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    archivos = st.file_uploader("Subir archivos PDF", type="pdf", accept_multiple_files=True, key=f"up_{st.session_state.uploader_id}")

    if archivos and st.button("⚡ Analizar Documentos"):
        st.session_state.pendientes = []
        for f in archivos:
            b = f.read()
            doc_id = hashlib.sha256(b).hexdigest()
            with fitz.open(stream=b, filetype="pdf") as pdf:
                raw = pdf[0].get_text() if len(pdf) > 0 else ""
                st.session_state.pendientes.append({
                    "id": doc_id, "nombre": f.name, "blob": b, 
                    "fecha": extraer_fecha_texto(raw), "tipo": tipo_up
                })

    if st.session_state.pendientes:
        st.subheader("📋 Revisión antes de guardar")
        if st.button("❌ Cancelar Carga"):
            st.session_state.pendientes = []
            st.session_state.uploader_id += 1
            st.rerun()
        
        docs_finales = []
        for i, d in enumerate(st.session_state.pendientes):
            with st.container():
                st.markdown('<div class="upload-card">', unsafe_allow_html=True)
                c_up1, c_up2 = st.columns([1, 2])
                with c_up1:
                    try: f_val = datetime.strptime(d['fecha'], "%Y-%m-%d").date()
                    except: f_val = datetime.now().date()
                    new_f = st.date_input(f"Fecha", value=f_val, key=f"f_up_{i}")
                with c_up2:
                    st.write(f"📄 **{d['nombre']}**")
                    st.caption(f"Tipo asignado: {d['tipo']}")
                docs_finales.append({**d, "fecha": new_f.strftime("%Y-%m-%d")})
                st.markdown('</div>', unsafe_allow_html=True)

        if st.button("🚀 Confirmar y Guardar todo"):
            for doc in docs_finales:
                full_t = ""
                p_map = {}
                with fitz.open(stream=doc['blob'], filetype="pdf") as pdf:
                    for idx, p in enumerate(pdf):
                        t = p.get_text().upper()
                        full_t += t + " "
                        p_map[idx+1] = t
                try:
                    c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)",
                             (doc['id'], doc['tipo'], "GENERAL", doc['fecha'], "PROVEEDOR", full_t, doc['nombre'], doc['blob'], json.dumps(p_map)))
                    conn.commit()
                except: pass
            st.success("¡Documentos almacenados correctamente!")
            st.session_state.pendientes = []
            st.session_state.uploader_id += 1
            st.rerun()

elif choice == "📂 Documentos":
    st.header("Inventario de Documentos")
    col_v1, col_v2 = st.columns(2)
    f_tipo = col_v1.selectbox("Filtrar por tipo:", ["Todos", "Factura de Compra", "Manifiesto de Aduana"])
    f_order = col_v2.selectbox("Ordenar por:", ["Más recientes primero", "Más antiguos primero"])
    
    order_sql = "DESC" if f_order == "Más recientes primero" else "ASC"
    if f_tipo == "Todos":
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos ORDER BY fecha_iso {order_sql}")
    else:
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE tipo=? ORDER BY fecha_iso {order_sql}", (f_tipo,))
    
    docs = c.fetchall()

    if docs:
        st.write(f"Mostrando {len(docs)} documentos.")
        for r in docs:
            fecha_v = datetime.strptime(r[3], "%Y-%m-%d").strftime("%d/%m/%Y")
            with st.expander(f"{fecha_v} | {r[1]} - {r[4]}"):
                render_editor_documento(r)
    else:
        st.info("No hay documentos registrados aún.")

elif choice == "🔍 Buscador":
    st.header("Buscador Inteligente Multitermino")
    query_in = st.text_input("Ingrese Referencias (sepárelas por coma)").upper()
    
    if query_in:
        queries = [q.strip() for q in query_in.split(",") if q.strip()]
        sql_cond = " OR ".join(["contenido LIKE ?" for _ in queries])
        params = [f"%{q}%" for q in queries]
        
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob, contenido FROM documentos WHERE {sql_cond} ORDER BY fecha_iso DESC", params)
        res = c.fetchall()
        
        if res:
            st.markdown(f'<div class="zip-download-container">', unsafe_allow_html=True)
            st.write(f"📂 **Acciones Masivas para {len(res)} resultados:**")
            cb1, cb2 = st.columns(2)
            
            zip_res = generar_zip_blob([r[:7] for r in res], True, queries)
            cb1.download_button("📥 Descargar Todos Subrayados (.zip)", zip_res, "busqueda_resaltada.zip")
            
            zip_orig = generar_zip_blob([r[:7] for r in res], False)
            cb2.download_button("📥 Descargar Todos Originales (.zip)", zip_orig, "busqueda_original.zip")
            st.markdown('</div>', unsafe_allow_html=True)
            
            for r in res:
                coinciden = [q for q in queries if q in r[7]]
                fecha_v = datetime.strptime(r[3], "%Y-%m-%d").strftime("%d/%m/%Y")
                with st.expander(f"🔍 {fecha_v} | {r[4]} (Coincide con: {', '.join(coinciden)})"):
                    render_editor_documento(r[:7], queries)
        else:
            st.warning("No se encontraron coincidencias para los términos ingresados.")
