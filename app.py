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
    
    .upload-card { border: 1px solid #3a3a4a; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: transparent; }
    .upload-card-error { border: 2px solid #dc3545; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: transparent; }
    
    .zip-download-container {
        padding: 0;
        margin-bottom: 25px;
    }

    /* Neutralizar borde blanco de st.container() en tema oscuro */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
    }

    /* Header de empresa en el buscador */
    .company-header {
        display: flex;
        align-items: center;
        gap: 22px;
        background: transparent;
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 14px;
        padding: 20px 28px;
        margin-bottom: 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .company-header img {
        height: 80px;
        width: 80px;
        object-fit: contain;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,0.2);
        background: white;
        padding: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    }
    .company-header-text h2 {
        margin: 0 0 4px 0;
        font-size: 1.7em;
        font-weight: 800;
        color: inherit;
        line-height: 1.2;
        letter-spacing: 0.02em;
    }
    .company-header-text span {
        font-size: 0.85em;
        color: inherit;
        font-weight: 400;
        opacity: 0.6;
    }
    .company-header-icon {
        font-size: 3.5em;
        line-height: 1;
    }

    /* Sidebar branding */
    .sidebar-brand {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 10px;
        padding: 10px 0 4px 0;
        text-align: center;
    }
    .sidebar-brand img {
        height: 96px;
        width: 96px;
        object-fit: contain;
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.15);
        background: white;
        padding: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    .sidebar-brand-name {
        font-size: 1em;
        font-weight: 700;
        color: inherit;
        line-height: 1.3;
        word-break: break-word;
        letter-spacing: 0.04em;
    }
    .sidebar-brand-icon {
        font-size: 3.5em;
    }

    /* Contadores en sidebar */
    .doc-counter-box {
        background: rgba(128,128,128,0.1);
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid rgba(128,128,128,0.2);
    }
    .doc-counter-label { font-size: 0.82em; color: inherit; font-weight: 500; opacity: 0.75; }
    .doc-counter-num { font-size: 1.15em; font-weight: 800; color: inherit; }

    /* Paginación */
    .pagination-info {
        text-align: center;
        color: #6c757d;
        font-size: 0.9em;
        margin: 8px 0 4px 0;
    }

    /* Botones Carga Masiva por clase wrapper */
    .btn-celeste button { background-color: #17a2b8 !important; color: white !important; border: none !important; }
    .btn-rojo button    { background-color: #dc3545 !important; color: white !important; border: none !important; }
    .btn-verde button   { background-color: #28a745 !important; color: white !important; border: none !important; }
    .btn-naranja button { background-color: #fd7e14 !important; color: white !important; border: none !important; }

    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTES Y BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('gestion_cronosol_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documentos 
                 (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha_iso TEXT, 
                  proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB, paginas_json TEXT)''')
    # Tabla de configuración de empresa
    c.execute('''CREATE TABLE IF NOT EXISTS config_empresa
                 (clave TEXT PRIMARY KEY, valor BLOB)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# --- FUNCIONES DE CONFIGURACIÓN DE EMPRESA ---

def guardar_config(clave, valor):
    c.execute("INSERT OR REPLACE INTO config_empresa (clave, valor) VALUES (?, ?)", (clave, valor))
    conn.commit()

def obtener_config(clave):
    c.execute("SELECT valor FROM config_empresa WHERE clave=?", (clave,))
    row = c.fetchone()
    return row[0] if row else None

def obtener_contadores():
    c.execute("SELECT tipo, COUNT(*) FROM documentos GROUP BY tipo")
    rows = c.fetchall()
    total = sum(r[1] for r in rows)
    mapa = {r[0]: r[1] for r in rows}
    return total, mapa

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

def abrir_pdf_js(bin_file, page_num=1, btn_id="", label="📄 Ver PDF", color="#007bff"):
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

# --- FUNCIÓN DE BÚSQUEDA CON CACHÉ EN SESSION STATE ---

def ejecutar_busqueda(queries):
    """Ejecuta la búsqueda y guarda resultados en session_state para evitar re-queries al paginar."""
    sql_cond = " OR ".join(["contenido LIKE ?" for _ in queries])
    params = [f"%{q}%" for q in queries]
    c.execute(
        f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob, contenido "
        f"FROM documentos WHERE {sql_cond} ORDER BY fecha_iso DESC",
        params
    )
    return c.fetchall()

# --- COMPONENTES DE BRANDING ---

def render_company_header():
    """Header de empresa para el módulo de Buscador."""
    nombre = obtener_config("nombre_empresa") or ""
    logo_blob = obtener_config("logo_empresa")

    if not nombre and not logo_blob:
        return  # Sin configuración, no mostrar nada

    if logo_blob:
        logo_b64 = base64.b64encode(logo_blob).decode('utf-8')
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Logo"/>'
    else:
        logo_html = '<div class="company-header-icon">🏢</div>'

    nombre_html = f"<h2>{nombre}</h2><span>Sistema de Trazabilidad Aduanera</span>" if nombre else "<h2>Mi Empresa</h2><span>Sistema de Trazabilidad Aduanera</span>"

    st.markdown(f"""
    <div class="company-header">
        {logo_html}
        <div class="company-header-text">
            {nombre_html}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar_brand():
    """Branding en el sidebar: logo + nombre + contadores."""
    nombre = obtener_config("nombre_empresa") or ""
    logo_blob = obtener_config("logo_empresa")
    total, mapa = obtener_contadores()

    # Logo o ícono
    if logo_blob:
        logo_b64 = base64.b64encode(logo_blob).decode('utf-8')
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Logo"/>'
    else:
        logo_html = '<div class="sidebar-brand-icon">🛡️</div>'

    nombre_html = f'<div class="sidebar-brand-name">{nombre}</div>' if nombre else ""

    st.markdown(f"""
    <div class="sidebar-brand">
        {logo_html}
        {nombre_html}
    </div>
    """, unsafe_allow_html=True)

    # Contadores
    st.markdown(f"""
    <div class="doc-counter-box">
        <span class="doc-counter-label">📄 Total documentos</span>
        <span class="doc-counter-num">{total}</span>
    </div>
    <div class="doc-counter-box">
        <span class="doc-counter-label">🧾 Facturas de Compra</span>
        <span class="doc-counter-num">{mapa.get('Factura de Compra', 0)}</span>
    </div>
    <div class="doc-counter-box">
        <span class="doc-counter-label">📋 Manifestos de Aduana</span>
        <span class="doc-counter-num">{mapa.get('Manifiesto de Aduana', 0)}</span>
    </div>
    """, unsafe_allow_html=True)

# --- INTERFAZ DE EDICIÓN ---

def render_editor_documento(r, search_terms=[], es_inventario=False):
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
        
        p_ini = min(p_encontradas) if p_encontradas else 1
        
        if not es_inventario and search_terms:
            c1, c2 = st.columns(2)
            with c1:
                pdf_resaltado = resaltar_pdf_multiple(blob, search_terms)
                st.components.v1.html(abrir_pdf_js(pdf_resaltado, p_ini, f"res_{doc_id}", f"Ver PDF Resaltado (Pág. {p_ini})", "#28a745"), height=65)
            with c2:
                st.components.v1.html(abrir_pdf_js(blob, p_ini, f"orig_{doc_id}", "Ver PDF Original", "#6c757d"), height=65)
        else:
            st.components.v1.html(abrir_pdf_js(blob, p_ini, f"orig_{doc_id}", "Ver PDF Original", "#007bff"), height=65)

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
if 'search_results' not in st.session_state: st.session_state.search_results = None
if 'last_query' not in st.session_state: st.session_state.last_query = ""
if 'search_page' not in st.session_state: st.session_state.search_page = 0
if 'inv_page' not in st.session_state: st.session_state.inv_page = 0

RESULTADOS_POR_PAGINA = 10

with st.sidebar:
    render_sidebar_brand()
    st.divider()
    choice = st.radio("Menú Principal", ["🔍 Buscador", "📂 Documentos", "📤 Carga Masiva", "⚙️ Personalización"])
    st.divider()
    st.info("Sistema de Trazabilidad Aduanera.")

# =============================================
# MÓDULO: PERSONALIZACIÓN
# =============================================
if choice == "⚙️ Personalización":
    st.header("⚙️ Personalización de la Aplicación")
    st.write("Configura el nombre y logo de tu empresa. Estos datos se muestran en el sidebar y en el módulo de búsqueda.")
    st.divider()

    nombre_actual = obtener_config("nombre_empresa") or ""
    logo_actual = obtener_config("logo_empresa")

    col_p1, col_p2 = st.columns([2, 1])

    with col_p1:
        st.subheader("🏢 Datos de la Empresa")
        nuevo_nombre = st.text_input("Nombre de la empresa", value=nombre_actual, placeholder="Ej: Cronosol S.A.S.")
        
        st.subheader("🖼️ Logo de la Empresa")
        st.caption("Formatos aceptados: PNG, JPG, JPEG. Recomendado: imagen cuadrada, mínimo 128×128 px.")
        logo_file = st.file_uploader("Subir logo", type=["png", "jpg", "jpeg"], label_visibility="collapsed")

        st.divider()
        if st.button("💾 Guardar Configuración", use_container_width=True):
            cambios = False
            if nuevo_nombre.strip():
                guardar_config("nombre_empresa", nuevo_nombre.strip())
                cambios = True
            if logo_file:
                guardar_config("logo_empresa", logo_file.read())
                cambios = True
            if cambios:
                st.success("✅ Configuración guardada correctamente. Los cambios son visibles de inmediato.")
                st.rerun()
            else:
                st.warning("No se realizaron cambios. Ingresa un nombre o sube un logo.")

        # Opción para limpiar logo
        if logo_actual:
            if st.button("🗑️ Eliminar logo actual", use_container_width=True):
                c.execute("DELETE FROM config_empresa WHERE clave='logo_empresa'")
                conn.commit()
                st.rerun()

    with col_p2:
        st.subheader("👁️ Vista Previa")
        preview_nombre = nuevo_nombre.strip() if nuevo_nombre.strip() else (nombre_actual or "Mi Empresa")
        
        if logo_file:
            logo_file.seek(0)
            logo_preview = logo_file.read()
            logo_b64 = base64.b64encode(logo_preview).decode('utf-8')
            preview_logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:56px;width:56px;object-fit:contain;border-radius:8px;border:1px solid #e9ecef;background:white;padding:4px;" alt="Logo"/>'
        elif logo_actual:
            logo_b64 = base64.b64encode(logo_actual).decode('utf-8')
            preview_logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height:56px;width:56px;object-fit:contain;border-radius:8px;border:1px solid #e9ecef;background:white;padding:4px;" alt="Logo"/>'
        else:
            preview_logo_html = '<div style="font-size:2.5em;">🏢</div>'

        st.markdown(f"""
        <div style="background:linear-gradient(90deg,#f8f9fa 0%,#ffffff 100%);border:1px solid #e0e0e0;border-radius:12px;padding:16px 20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
            <div style="display:flex;align-items:center;gap:14px;">
                {preview_logo_html}
                <div>
                    <div style="font-weight:700;font-size:1.1em;color:#1a1a2e;">{preview_nombre}</div>
                    <div style="font-size:0.8em;color:#6c757d;">Sistema de Trazabilidad Aduanera</div>
                </div>
            </div>
        </div>
        <p style="font-size:0.75em;color:#aaa;margin-top:8px;text-align:center;">Vista previa del header en Buscador</p>
        """, unsafe_allow_html=True)

# =============================================
# MÓDULO: CARGA MASIVA
# =============================================
elif choice == "📤 Carga Masiva":
    st.header("Carga Masiva de Documentos")
    tipo_up = st.radio("Tipo de Documento:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    archivos = st.file_uploader("Subir archivos PDF", type="pdf", accept_multiple_files=True, key=f"up_{st.session_state.uploader_id}")

    st.markdown('<div class="btn-celeste">', unsafe_allow_html=True)
    analizar_clicked = st.button("⚡ Analizar Documentos", key="btn_analizar")
    st.markdown('</div>', unsafe_allow_html=True)
    if analizar_clicked:
        st.session_state.pendientes = []
        for f in archivos:
            b = f.read()
            doc_id = hashlib.sha256(b).hexdigest()
            with fitz.open(stream=b, filetype="pdf") as pdf:
                full_text = ""
                for page in pdf:
                    full_text += page.get_text()
                tiene_ocr = len(full_text.strip()) > 5
                st.session_state.pendientes.append({
                    "id": doc_id, 
                    "nombre": f.name, 
                    "blob": b, 
                    "fecha": extraer_fecha_texto(full_text), 
                    "tipo": tipo_up,
                    "ocr": tiene_ocr
                })

    if st.session_state.pendientes:
        st.subheader("📋 Revisión antes de guardar")
        hay_errores_ocr = any(not d['ocr'] for d in st.session_state.pendientes)
        
        docs_finales = []
        for i, d in enumerate(st.session_state.pendientes):
            c_up1, c_up2 = st.columns([1, 2])
            with c_up1:
                if d['ocr']:
                    try: f_val = datetime.strptime(d['fecha'], "%Y-%m-%d").date()
                    except: f_val = datetime.now().date()
                    new_f = st.date_input(f"Fecha", value=f_val, key=f"f_up_{i}")
                else:
                    st.error("⚠️ ERROR: Sin OCR")
            with c_up2:
                st.write(f"📄 **{d['nombre']}**")
                if not d['ocr']:
                    st.markdown("<small style='color:red;'>Este documento no tiene texto extraíble. Por favor, súbelo de nuevo con OCR o elimínalo.</small>", unsafe_allow_html=True)
                else:
                    st.caption(f"Tipo asignado: {d['tipo']}")
            if d['ocr']:
                docs_finales.append({**d, "fecha": new_f.strftime("%Y-%m-%d")})
            st.divider()

        if hay_errores_ocr:
            st.warning("Debe corregir o eliminar los archivos sin OCR para poder continuar.")
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                st.markdown('<div class="btn-rojo">', unsafe_allow_html=True)
                cancel_ocr_clicked = st.button("❌ Cancelar Carga", key="cancel_ocr")
                st.markdown('</div>', unsafe_allow_html=True)
                if cancel_ocr_clicked:
                    st.session_state.pendientes = []
                    st.session_state.uploader_id += 1
                    st.rerun()
            with btn_col2:
                st.markdown('<div class="btn-naranja">', unsafe_allow_html=True)
                quitar_clicked = st.button("🗑️ Quitar archivos con error", key="btn_quitar_error")
                st.markdown('</div>', unsafe_allow_html=True)
                if quitar_clicked:
                    st.session_state.pendientes = [d for d in st.session_state.pendientes if d['ocr']]
                    st.rerun()
        else:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                st.markdown('<div class="btn-rojo">', unsafe_allow_html=True)
                cancel_ok_clicked = st.button("❌ Cancelar Carga", key="cancel_ok")
                st.markdown('</div>', unsafe_allow_html=True)
                if cancel_ok_clicked:
                    st.session_state.pendientes = []
                    st.session_state.uploader_id += 1
                    st.rerun()
            with btn_col2:
                st.markdown('<div class="btn-verde">', unsafe_allow_html=True)
                confirmar_clicked = st.button("🚀 Confirmar y Guardar todo", key="btn_confirmar")
                st.markdown('</div>', unsafe_allow_html=True)
                if confirmar_clicked:
                    for doc in docs_finales:
                        full_t = ""
                        p_map = {}
                        with fitz.open(stream=doc['blob'], filetype="pdf") as pdf:
                            for idx, p in enumerate(pdf):
                                t = p.get_text().upper()
                                full_t += t + " "
                                p_map[idx+1] = t
                        try:
                            c.execute("INSERT INTO documentos (id, tipo, numero, fecha_iso, proveedor, contenido, nombre_archivo, pdf_blob, paginas_json) VALUES (?,?,?,?,?,?,?,?,?)",
                                     (doc['id'], doc['tipo'], "GENERAL", doc['fecha'], "PROVEEDOR", full_t, doc['nombre'], doc['blob'], json.dumps(p_map)))
                            conn.commit()
                        except: pass
                    st.success("¡Documentos almacenados correctamente!")
                    st.session_state.pendientes = []
                    st.session_state.uploader_id += 1
                    st.rerun()

# =============================================
# MÓDULO: INVENTARIO
# =============================================
elif choice == "📂 Documentos":
    st.header("Inventario de Documentos")
    col_v1, col_v2 = st.columns(2)
    f_tipo = col_v1.selectbox("Filtrar por tipo:", ["Todos", "Factura de Compra", "Manifiesto de Aduana"])
    f_order = col_v2.selectbox("Ordenar por:", ["Más recientes primero", "Más antiguos primero"])

    # Reset página al cambiar filtros
    filtro_key = f"{f_tipo}_{f_order}"
    if 'inv_filtro_key' not in st.session_state or st.session_state.inv_filtro_key != filtro_key:
        st.session_state.inv_page = 0
        st.session_state.inv_filtro_key = filtro_key

    order_sql = "DESC" if f_order == "Más recientes primero" else "ASC"
    INV_POR_PAGINA = 100

    # Contar total para paginación y ZIP (sin LIMIT)
    if f_tipo == "Todos":
        c.execute(f"SELECT COUNT(*) FROM documentos")
        total_inv = c.fetchone()[0]
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos ORDER BY fecha_iso {order_sql}")
        docs_todos = c.fetchall()
    else:
        c.execute(f"SELECT COUNT(*) FROM documentos WHERE tipo=?", (f_tipo,))
        total_inv = c.fetchone()[0]
        c.execute(f"SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob FROM documentos WHERE tipo=? ORDER BY fecha_iso {order_sql}", (f_tipo,))
        docs_todos = c.fetchall()

    if docs_todos:
        # ZIP siempre sobre todos los resultados del filtro activo
        st.markdown('<div class="zip-download-container">', unsafe_allow_html=True)
        label_zip = f"Descargar {f_tipo}" if f_tipo != "Todos" else "Descargar Todo el Inventario"
        zip_data = generar_zip_blob(docs_todos)
        st.write(f"📦 **Acciones para {total_inv} documentos encontrados:**")
        st.download_button(f"📥 {label_zip} (.zip)", zip_data, f"{f_tipo.lower().replace(' ','_')}.zip")
        st.markdown('</div>', unsafe_allow_html=True)

        # Slicing para la página actual
        inv_pagina_actual = st.session_state.inv_page
        inv_total_paginas = (total_inv + INV_POR_PAGINA - 1) // INV_POR_PAGINA
        inv_inicio = inv_pagina_actual * INV_POR_PAGINA
        inv_fin = inv_inicio + INV_POR_PAGINA
        docs_pagina = docs_todos[inv_inicio:inv_fin]

        for r in docs_pagina:
            fecha_v = datetime.strptime(r[3], "%Y-%m-%d").strftime("%d/%m/%Y")
            with st.expander(f"{fecha_v} | {r[1]} - {r[4]}"):
                render_editor_documento(r, es_inventario=True)

        # Controles de paginación
        if inv_total_paginas > 1:
            st.divider()
            st.markdown(f'<div class="pagination-info">Página {inv_pagina_actual + 1} de {inv_total_paginas} — Mostrando {inv_inicio + 1}–{min(inv_fin, total_inv)} de {total_inv}</div>', unsafe_allow_html=True)
            pag_col1, pag_col2, pag_col3 = st.columns([1, 2, 1])
            with pag_col1:
                if inv_pagina_actual > 0:
                    if st.button("← Anterior", key="inv_prev", use_container_width=True):
                        st.session_state.inv_page -= 1
                        st.rerun()
            with pag_col3:
                if inv_pagina_actual < inv_total_paginas - 1:
                    if st.button("Siguiente →", key="inv_next", use_container_width=True):
                        st.session_state.inv_page += 1
                        st.rerun()
    else:
        st.info("No hay documentos registrados aún en esta categoría.")

    # --- ZONA DE DEPURACIÓN MASIVA ---
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("⚠️ Depuración Masiva — Eliminar documentos por rango de fechas"):
        st.warning("**Zona de riesgo.** Esta acción es irreversible. Los documentos eliminados no se pueden recuperar.")
        st.divider()

        # PASO 1: Filtros
        st.markdown("**Paso 1 — Definir filtros**")
        dep_col1, dep_col2, dep_col3 = st.columns(3)
        dep_desde = dep_col1.date_input("Desde", value=datetime(2020, 1, 1).date(), key="dep_desde")
        dep_hasta = dep_col2.date_input("Hasta", value=datetime.now().date(), key="dep_hasta")
        dep_tipo = dep_col3.selectbox("Tipo de documento", ["Todos", "Factura de Compra", "Manifiesto de Aduana"], key="dep_tipo")

        if dep_desde > dep_hasta:
            st.error("La fecha 'Desde' no puede ser posterior a la fecha 'Hasta'.")
        else:
            # Query de preview en tiempo real
            desde_str = dep_desde.strftime("%Y-%m-%d")
            hasta_str = dep_hasta.strftime("%Y-%m-%d")

            if dep_tipo == "Todos":
                c.execute(
                    "SELECT id, tipo, fecha_iso, nombre_archivo FROM documentos WHERE fecha_iso >= ? AND fecha_iso <= ? ORDER BY fecha_iso ASC",
                    (desde_str, hasta_str)
                )
            else:
                c.execute(
                    "SELECT id, tipo, fecha_iso, nombre_archivo FROM documentos WHERE fecha_iso >= ? AND fecha_iso <= ? AND tipo = ? ORDER BY fecha_iso ASC",
                    (desde_str, hasta_str, dep_tipo)
                )
            docs_a_eliminar = c.fetchall()

            if not docs_a_eliminar:
                st.info("Ningún documento coincide con los filtros seleccionados.")
            else:
                st.markdown(f"**Paso 2 — Preview:** Se eliminarían **{len(docs_a_eliminar)} documento(s)**")

                # Lista de documentos afectados
                with st.expander(f"Ver los {len(docs_a_eliminar)} documento(s) que serán eliminados"):
                    for d in docs_a_eliminar:
                        fecha_v = datetime.strptime(d[2], "%Y-%m-%d").strftime("%d/%m/%Y")
                        st.markdown(f"- `{fecha_v}` · {d[1]} · **{d[3]}**")

                st.divider()

                # PASO 3: Confirmación
                st.markdown("**Paso 3 — Confirmación**")
                st.markdown("Para ejecutar la eliminación, escribe exactamente: `CONFIRMAR ELIMINACIÓN`")
                frase = st.text_input("Frase de confirmación", key="dep_frase", placeholder="CONFIRMAR ELIMINACIÓN")

                if frase == "CONFIRMAR ELIMINACIÓN":
                    if st.button("🗑️ Ejecutar eliminación masiva", key="dep_ejecutar"):
                        ids = [d[0] for d in docs_a_eliminar]
                        c.execute(
                            f"DELETE FROM documentos WHERE id IN ({','.join(['?']*len(ids))})",
                            ids
                        )
                        conn.commit()
                        st.success(f"✅ {len(ids)} documento(s) eliminado(s) correctamente.")
                        st.rerun()
                elif frase:
                    st.error("La frase no coincide. Verifica mayúsculas y tildes.")

# =============================================
# MÓDULO: BUSCADOR (con caché + paginación + filtro)
# =============================================
elif choice == "🔍 Buscador":
    render_company_header()
    st.header("Buscador Inteligente Multitermino")
    query_in = st.text_input("Ingrese Referencias (sepárelas por coma)").upper()

    if query_in:
        queries = [q.strip() for q in query_in.split(",") if q.strip()]

        # Caché: solo ejecutar query si cambió el término de búsqueda
        if query_in != st.session_state.last_query:
            st.session_state.search_results = ejecutar_busqueda(queries)
            st.session_state.last_query = query_in
            st.session_state.search_page = 0

        res_completo = st.session_state.search_results

        if res_completo:
            # --- SWITCHES DE FILTRO ---
            st.write("**Filtrar por tipo:**")
            sw1, sw2, _ = st.columns([1.4, 1.8, 3])
            with sw1:
                mostrar_facturas = st.toggle("Facturas de Compra", value=True, key="sw_facturas")
            with sw2:
                mostrar_manifiestos = st.toggle("Manifiestos de Aduana", value=True, key="sw_manifiestos")

            # Aplicar filtro en memoria según estado de los switches
            if mostrar_facturas and mostrar_manifiestos:
                res = res_completo
                label_filtro = ""
            elif mostrar_facturas:
                res = [r for r in res_completo if r[1] == "Factura de Compra"]
                label_filtro = " · Facturas de Compra"
            elif mostrar_manifiestos:
                res = [r for r in res_completo if r[1] == "Manifiesto de Aduana"]
                label_filtro = " · Manifiestos de Aduana"
            else:
                res = []
                label_filtro = ""

            if res:
                total_resultados = len(res)
                total_paginas = (total_resultados + RESULTADOS_POR_PAGINA - 1) // RESULTADOS_POR_PAGINA
                pagina_actual = st.session_state.search_page
                inicio = pagina_actual * RESULTADOS_POR_PAGINA
                fin = inicio + RESULTADOS_POR_PAGINA
                res_pagina = res[inicio:fin]

                # Acciones masivas (sobre resultados filtrados)
                st.markdown('<div class="zip-download-container">', unsafe_allow_html=True)
                st.write(f"📂 **{total_resultados} resultado(s){label_filtro}** — Mostrando {inicio+1}–{min(fin, total_resultados)}")
                cb1, cb2 = st.columns(2)
                zip_res = generar_zip_blob([r[:7] for r in res], True, queries)
                cb1.download_button("📥 Descargar Resultados Subrayados (.zip)", zip_res, "busqueda_resaltada.zip")
                zip_orig = generar_zip_blob([r[:7] for r in res], False)
                cb2.download_button("📥 Descargar Resultados Originales (.zip)", zip_orig, "busqueda_original.zip")
                st.markdown('</div>', unsafe_allow_html=True)

                # Resultados de la página actual
                for r in res_pagina:
                    coinciden = [q for q in queries if q in r[7]]
                    fecha_v = datetime.strptime(r[3], "%Y-%m-%d").strftime("%d/%m/%Y")
                    with st.expander(f"🔍 {fecha_v} | {r[4]} (Coincide con: {', '.join(coinciden)})"):
                        render_editor_documento(r[:7], queries, es_inventario=False)

                # Controles de paginación
                if total_paginas > 1:
                    st.divider()
                    st.markdown(f'<div class="pagination-info">Página {pagina_actual + 1} de {total_paginas}</div>', unsafe_allow_html=True)
                    nav1, nav2, nav3 = st.columns([1, 2, 1])
                    with nav1:
                        if pagina_actual > 0:
                            if st.button("← Anterior", use_container_width=True):
                                st.session_state.search_page -= 1
                                st.rerun()
                    with nav3:
                        if pagina_actual < total_paginas - 1:
                            if st.button("Siguiente →", use_container_width=True):
                                st.session_state.search_page += 1
                                st.rerun()
            else:
                if not mostrar_facturas and not mostrar_manifiestos:
                    st.warning("⚠️ Activa al menos un filtro para ver resultados.")
                else:
                    st.info(f"No hay resultados{label_filtro} para esta búsqueda.")
        else:
            st.error("No se encontraron coincidencias para los términos ingresados.")
