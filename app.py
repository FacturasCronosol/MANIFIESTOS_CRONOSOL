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

# Estilo personalizado para botones y tarjetas
st.markdown("""
    <style>
    /* Botón general */
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; }
    
    /* Botón de Guardar (Verde) */
    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] .stButton button[key*="save_"] {
        background-color: #28a745 !important;
        color: white !important;
        border: none;
    }

    /* Botón de Eliminar (Rojo) */
    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] .stButton button[key*="del_"] {
        background-color: #dc3545 !important;
        color: white !important;
        border: none;
    }
    
    .stDownloadButton>button { background-color: #007bff !important; color: white !important; }

    .highlight-page { background-color: #fff3cd; padding: 5px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .ocr-warning { background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; border-left: 5px solid #dc3545; font-weight: bold; margin-top: 5px; }
    .cancel-btn button { background-color: #6c757d !important; color: white !important; }
    
    /* Estilo para los botones de descarga ZIP */
    .zip-btn button { background-color: #6f42c1 !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# Diccionarios de fechas
MESES_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"
}

MESES_NOMBRE_A_NUM = {
    'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04', 'MAYO': '05', 'JUNIO': '06',
    'JULIO': '07', 'AGOSTO': '08', 'SEPTIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12',
    'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AGO': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12'
}

# Inicialización de la base de datos
def init_db():
    db_path = 'gestion_cronosol_v4.db' 
    conn = sqlite3.connect(db_path, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documentos 
                 (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha_iso TEXT, 
                  proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB, paginas_json TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# --- FUNCIONES DE GESTIÓN ---

def actualizar_documento(doc_id, nuevo_tipo, nuevo_nombre, nueva_fecha):
    c.execute("""UPDATE documentos 
                 SET tipo=?, nombre_archivo=?, fecha_iso=? 
                 WHERE id=?""", (nuevo_tipo, nuevo_nombre, nueva_fecha, doc_id))
    conn.commit()

def eliminar_documento(doc_id):
    c.execute("DELETE FROM documentos WHERE id=?", (doc_id,))
    conn.commit()

def resaltar_pdf_multiple(pdf_bytes, queries):
    if not queries:
        return pdf_bytes
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            for q in queries:
                if q.strip():
                    text_instances = page.search_for(q.strip())
                    for inst in text_instances:
                        annot = page.add_highlight_annot(inst)
                        annot.update()
        output_bytes = doc.write()
        doc.close()
        return output_bytes
    except Exception:
        return pdf_bytes

def formatear_fecha_visual(fecha_iso):
    try:
        dt = datetime.strptime(fecha_iso, "%Y-%m-%d")
        return f"{dt.day}/{MESES_ES[dt.month]}/{dt.year}"
    except:
        return fecha_iso

def normalizar_fecha_a_iso(texto_fecha):
    if not texto_fecha:
        return datetime.now().strftime("%Y-%m-%d")
    if isinstance(texto_fecha, (datetime, pd.Timestamp)):
        return texto_fecha.strftime("%Y-%m-%d")

    texto_fecha = str(texto_fecha).upper().replace("DE ", " ").replace(".", "").replace(",", "").strip()
    texto_fecha = re.sub(r'[^A-Z0-9/\-\s]', '', texto_fecha) 
    texto_fecha = re.sub(r'\s+', ' ', texto_fecha)
    
    m1 = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', texto_fecha)
    if m1:
        d, m, y = m1.groups()
        try: return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except: pass
        
    m2 = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', texto_fecha)
    if m2:
        y, m, d = m2.groups()
        try: return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except: pass

    m3 = re.search(r'(\d{1,2})\s+([A-Z]{3,10})\s+(\d{4})', texto_fecha)
    if m3:
        d, mes_nombre, y = m3.groups()
        if mes_nombre in MESES_NOMBRE_A_NUM:
            m = MESES_NOMBRE_A_NUM[mes_nombre]
            return f"{int(y):04d}-{m}-{int(d):02d}"

    if re.match(r'^\d{4}-\d{2}-\d{2}$', texto_fecha):
        return texto_fecha
    return datetime.now().strftime("%Y-%m-%d")

def extraer_fecha_texto(texto):
    texto_limpio = texto.upper()
    patrones = [r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})', r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})', r'(\d{1,2}\s+[A-Z]{3,10}\s+\d{4})']
    for pat in patrones:
        match = re.search(pat, texto_limpio)
        if match:
            return normalizar_fecha_a_iso(match.group(0))
    return datetime.now().strftime("%Y-%m-%d")

def abrir_pdf_js(bin_file, page_num=1, btn_id=""):
    base64_pdf = base64.b64encode(bin_file).decode('utf-8')
    js = f"""
    <script>
    function openPDF_{btn_id}() {{
        const byteCharacters = atob("{base64_pdf}");
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {{ byteNumbers[i] = byteCharacters.charCodeAt(i); }}
        const byteArray = new Uint8Array(byteNumbers);
        const file = new Blob([byteArray], {{type: 'application/pdf'}});
        const fileURL = URL.createObjectURL(file);
        window.open(fileURL + '#page={page_num}', '_blank');
    }}
    </script>
    <button onclick="openPDF_{btn_id}()" style="
        width: 100%; padding: 0.75em 1.5em; background-color: #28a745; color: white;
        border: none; border-radius: 8px; font-weight: bold; cursor: pointer;
    ">📄 Ver PDF Resaltado (Pág. {page_num})</button>
    """
    return js

def generar_zip_documentos(tipo_filtro):
    # Obtener documentos de la DB según el tipo
    c.execute("SELECT nombre_archivo, pdf_blob FROM documentos WHERE tipo=?", (tipo_filtro,))
    docs = c.fetchall()
    
    if not docs:
        return None
    
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nombre, blob in docs:
            # Aseguramos que el nombre termine en .pdf
            fname = nombre if nombre.lower().endswith(".pdf") else f"{nombre}.pdf"
            zf.writestr(fname, blob)
    
    return buf.getvalue()

# --- COMPONENTE DE EDICIÓN (REUTILIZABLE) ---
def render_editor_documento(r):
    doc_id, tipo, num, fecha_iso, nombre, pags, blob = r
    tab1, tab2 = st.tabs(["📄 Ver / Resultados", "⚙️ Gestionar Datos"])
    
    with tab1:
        # Lógica de resaltado (soporta múltiples queries si vienen del buscador)
        search_terms = st.session_state.get('last_queries', [])
        p_dict = json.loads(pags)
        
        paginas_encontradas = []
        if search_terms:
            for p, cont in p_dict.items():
                if any(q.strip() in cont for q in search_terms if q.strip()):
                    paginas_encontradas.append(p)
        
        if paginas_encontradas:
            st.markdown(f'<div class="highlight-page">📍 Términos encontrados en pág: {", ".join(map(str, sorted(list(set(paginas_encontradas)))))}</div>', unsafe_allow_html=True)
        
        pdf_final = resaltar_pdf_multiple(blob, search_terms)
        p_inicial = paginas_encontradas[0] if paginas_encontradas else 1
        
        st.components.v1.html(abrir_pdf_js(pdf_final, p_inicial, btn_id=doc_id), height=70)
        st.download_button("💾 Descargar PDF", pdf_final, f"DOC_{nombre}", "application/pdf", key=f"dl_{doc_id}")

    with tab2:
        edit_nombre = st.text_input("Nombre del archivo", value=nombre, key=f"n_{doc_id}")
        c_e1, c_e2 = st.columns(2)
        edit_tipo = c_e1.selectbox("Tipo de Documento", ["Factura de Compra", "Manifiesto de Aduana"], index=0 if tipo=="Factura de Compra" else 1, key=f"t_{doc_id}")
        try: f_edit_dt = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
        except: f_edit_dt = datetime.now().date()
        edit_fecha = c_e2.date_input("Fecha", value=f_edit_dt, key=f_edit_doc_id if 'f_edit_doc_id' in locals() else f"f_edit_ui_{doc_id}")
        
        st.divider()
        col_btn_del, col_btn_save = st.columns(2)
        
        if f"confirm_del_{doc_id}" not in st.session_state:
            if col_btn_del.button("🗑️ Eliminar Documento", key=f"del_{doc_id}"):
                st.session_state[f"confirm_del_{doc_id}"] = True
                st.rerun()
        else:
            st.error("¿Confirmar eliminación definitiva?")
            if col_btn_del.button("✅ Confirmar", key=f"confirm_del_btn_{doc_id}"):
                eliminar_documento(doc_id)
                st.rerun()
            if st.button("❌ Cancelar", key=f"cancel_del_{doc_id}"):
                del st.session_state[f"confirm_del_{doc_id}"]
                st.rerun()

        if col_btn_save.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
            actualizar_documento(doc_id, edit_tipo, edit_nombre, edit_fecha.strftime("%Y-%m-%d"))
            st.success("¡Documento actualizado!")
            st.rerun()

# --- INTERFAZ ---
if 'pendientes' not in st.session_state:
    st.session_state.pendientes = []
if 'uploader_id' not in st.session_state:
    st.session_state.uploader_id = 0
if 'last_queries' not in st.session_state:
    st.session_state.last_queries = []

def limpiar_carga_total():
    st.session_state.pendientes = []
    st.session_state.uploader_id += 1

with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Menú", ["🔍 Buscador", "📂 Documentos", "📤 Carga Masiva"])
    st.divider()
    st.info("Sistema de Trazabilidad Aduanera.")

if choice == "📤 Carga Masiva":
    st.header("Carga Masiva de Documentos")
    tipo_doc = st.radio("Tipo de Documento:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    archivos = st.file_uploader("Subir archivos PDF", type="pdf", accept_multiple_files=True, key=f"uploader_{st.session_state.uploader_id}")

    if archivos:
        if st.button("⚡ Analizar Documentos"):
            st.session_state.pendientes = []
            for f in archivos:
                pdf_bytes = f.read()
                doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    raw_text = doc[0].get_text() if len(doc) > 0 else ""
                    st.session_state.pendientes.append({
                        "id": doc_id, "nombre": f.name, "tipo": tipo_doc,
                        "fecha_iso": extraer_fecha_texto(raw_text), "blob": pdf_bytes,
                        "ocr_warning": len(raw_text.strip()) < 50
                    })

        if st.session_state.pendientes:
            st.subheader("📋 Revisión de Datos")
            if st.button("❌ Cancelar Carga", key="cancel_main"):
                limpiar_carga_total()
                st.rerun()
            
            documentos_finales = []
            for i, d in enumerate(st.session_state.pendientes):
                with st.container():
                    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        try: fecha_dt = datetime.strptime(d['fecha_iso'], "%Y-%m-%d").date()
                        except: fecha_dt = datetime.now().date()
                        f_input = st.date_input(f"Fecha", value=fecha_dt, key=f"f_{i}")
                    with col2:
                        st.write(f"📄 **{d['nombre']}**")
                        if d.get("ocr_warning"): st.warning("⚠️ Sin texto detectable.")
                    documentos_finales.append({**d, "fecha_iso": f_input.strftime("%Y-%m-%d")})
                    st.markdown('</div>', unsafe_allow_html=True)

            if st.button("🚀 Guardar en Base de Datos"):
                for doc in documentos_finales:
                    texto_full = ""
                    dict_pags = {}
                    with fitz.open(stream=doc['blob'], filetype="pdf") as pdf:
                        for p_idx, pagina in enumerate(pdf):
                            t = pagina.get_text().upper()
                            texto_full += t + " "
                            dict_pags[p_idx+1] = t
                    try:
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?,?)", 
                                 (doc['id'], doc['tipo'], doc['nombre'], doc['fecha_iso'], "GENERAL", texto_full, doc['nombre'], doc['blob'], json.dumps(dict_pags)))
                        conn.commit()
                    except: pass
                st.success("¡Guardado!")
                limpiar_carga_total()
                st.rerun()

elif choice == "📂 Documentos":
    st.header("Inventario de Documentos")
    
    # --- FILTROS DE VISTA ---
    with st.container():
        f1, f2, f3 = st.columns([2, 2, 2])
        filtro_tipo = f1.selectbox("Filtrar por tipo:", ["Todos", "Factura de Compra", "Manifiesto de Aduana"])
        filtro_orden = f2.selectbox("Ordenar por fecha:", ["Más recientes primero", "Más antiguos primero"])
        
        # Lógica de SQL según filtros
        order_sql = "DESC" if filtro_orden == "Más recientes primero" else "ASC"
        if filtro_tipo == "Todos":
            query_sql = f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos ORDER BY fecha_iso {order_sql}"
            params = ()
        else:
            query_sql = f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE tipo=? ORDER BY fecha_iso {order_sql}"
            params = (filtro_tipo,)
            
        c.execute(query_sql, params)
        todos = c.fetchall()
    
    st.divider()
    
    # --- BOTONES DE DESCARGA MASIVA ---
    col_zip1, col_zip2 = st.columns(2)
    
    # Descargar Facturas
    zip_facturas = generar_zip_documentos("Factura de Compra")
    if zip_facturas:
        col_zip1.download_button(
            label="📦 Descargar todas las Facturas (.zip)",
            data=zip_facturas,
            file_name=f"Facturas_Cronosol_{datetime.now().strftime('%Y%m%d')}.zip",
            mime="application/zip",
            key="btn_zip_facturas"
        )
    else:
        col_zip1.button("📦 Sin Facturas para descargar", disabled=True)
        
    # Descargar Manifiestos
    zip_manifiestos = generar_zip_documentos("Manifiesto de Aduana")
    if zip_manifiestos:
        col_zip2.download_button(
            label="📦 Descargar todos los Manifiestos (.zip)",
            data=zip_manifiestos,
            file_name=f"Manifiestos_Cronosol_{datetime.now().strftime('%Y%m%d')}.zip",
            mime="application/zip",
            key="btn_zip_manifiestos"
        )
    else:
        col_zip2.button("📦 Sin Manifiestos para descargar", disabled=True)

    st.divider()

    if todos:
        st.write(f"Mostrando **{len(todos)}** documentos encontrados.")
        st.session_state.last_queries = [] 
        for r in todos:
            with st.expander(f"{formatear_fecha_visual(r[3])} | {r[1]} - {r[4]}"):
                render_editor_documento(r)
    else:
        st.info("No hay documentos que coincidan con el filtro seleccionado.")

elif choice == "🔍 Buscador":
    st.header("Buscador Multitermino")
    st.info("💡 Puedes buscar varias referencias separadas por coma. Ejemplo: `REF123, REF456, CONTENEDOR789`")
    raw_query = st.text_input("Ingrese Referencias o Palabras Clave").upper()

    if raw_query:
        # Separar por comas y limpiar espacios
        queries = [q.strip() for q in raw_query.split(",") if q.strip()]
        st.session_state.last_queries = queries
        
        # Construir consulta SQL dinámica para buscar cualquiera de los términos
        sql_conditions = " OR ".join(["contenido LIKE ?" for _ in queries])
        sql_params = [f"%{q}%" for q in queries]
        
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob, contenido FROM documentos WHERE {sql_conditions} ORDER BY fecha_iso DESC", sql_params)
        res = c.fetchall()
        
        if res:
            st.write(f"Resultados encontrados: **{len(res)}**")
            for r in res:
                doc_id, tipo, num, fecha_iso, nombre, pags, blob, contenido = r
                
                # Detectar cuáles de las queries están presentes en este documento específico
                coincidencias = [q for q in queries if q in contenido]
                str_coincidencias = f"({', '.join(coincidencias)})" if coincidencias else ""
                
                # Mostrar el expander con las coincidencias en el título
                with st.expander(f"🔍 {formatear_fecha_visual(fecha_iso)} | {tipo} - {nombre} {str_coincidencias}"):
                    # Pasamos solo los primeros 7 elementos de r para que coincida con la firma de render_editor_documento
                    render_editor_documento(r[:7])
        else:
            st.warning("No se encontraron coincidencias para los términos ingresados.")
