import streamlit as st
import fitz  # PyMuPDF
import hashlib
import base64
import json
import re
import zipfile
from io import BytesIO
from datetime import datetime
from supabase import create_client, Client

# Configuración profesional de la página
st.set_page_config(
    page_title="CRONOSOL - DIAN", 
    layout="wide", 
    page_icon="🟡"
)

# --- ESTILOS PERSONALIZADOS ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; }
    
    /* Botones editor de documento */
    [class*="st-key-del_"] button   { background-color: #dc3545 !important; color: white !important; border: none !important; }
    [class*="st-key-save_"] button  { background-color: #28a745 !important; color: white !important; border: none !important; }
    [class*="st-key-c_ok_"] button  { background-color: #dc3545 !important; color: white !important; border: none !important; }
    [class*="st-key-c_no_"] button  { background-color: #007bff !important; color: white !important; border: none !important; }
    
    .stDownloadButton>button { background-color: #007bff !important; color: white !important; }

    .highlight-page { background-color: #e8f4fd; padding: 10px; border-radius: 5px; border-left: 5px solid #007bff; font-weight: bold; margin-bottom: 10px; color: #0056b3; }
    
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

    /* Botones Carga Masiva */
    .st-key-btn_analizar button  { background-color: #007bff !important; color: white !important; border: none !important; }
    .st-key-cancel_ocr button,
    .st-key-cancel_ok button     { background-color: #dc3545 !important; color: white !important; border: none !important; }
    .st-key-btn_confirmar button { background-color: #28a745 !important; color: white !important; border: none !important; }
    .st-key-btn_quitar_error button { background-color: #fd7e14 !important; color: white !important; border: none !important; }

    /* Botones Personalización */
    .st-key-btn_guardar_config button  { background-color: #28a745 !important; color: white !important; border: none !important; }
    .st-key-btn_eliminar_logo button   { background-color: #dc3545 !important; color: white !important; border: none !important; }

    /* Botón Depuración Masiva */
    .st-key-dep_ejecutar button { background-color: #dc3545 !important; color: white !important; border: none !important; }

    </style>
    """, unsafe_allow_html=True)


# =============================================
# CONEXIÓN A SUPABASE
# =============================================

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()
BUCKET = "documentos-pdf"


# =============================================
# FUNCIONES DE CONFIGURACIÓN DE EMPRESA
# =============================================

def guardar_config(clave: str, valor):
    """Guarda o actualiza un valor en config_empresa."""
    if isinstance(valor, (bytes, bytearray)):
        valor_b64 = base64.b64encode(valor).decode("utf-8")
    else:
        valor_b64 = valor
    supabase.table("config_empresa").upsert({"clave": clave, "valor": valor_b64}).execute()

def obtener_config(clave: str):
    """Obtiene un valor de config_empresa. Devuelve bytes si era binario, str si era texto."""
    res = supabase.table("config_empresa").select("valor").eq("clave", clave).execute()
    if res.data:
        val = res.data[0]["valor"]
        # Intentar decodificar como base64 (logos)
        try:
            return base64.b64decode(val)
        except Exception:
            return val
    return None

def obtener_contadores():
    """Devuelve (total, {tipo: count}) consultando Supabase."""
    res = supabase.table("documentos").select("tipo").execute()
    rows = res.data or []
    total = len(rows)
    mapa = {}
    for r in rows:
        t = r["tipo"]
        mapa[t] = mapa.get(t, 0) + 1
    return total, mapa


# =============================================
# FUNCIONES DE PROCESAMIENTO PDF
# =============================================

def resaltar_pdf_multiple(pdf_bytes, queries):
    if not queries:
        return pdf_bytes
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
    except:
        return pdf_bytes

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
    patrones = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
        r'(\d{1,2}\s+[A-Z]{3,10}\s+\d{4})'
    ]
    for pat in patrones:
        match = re.search(pat, texto_limpio)
        if match:
            f = match.group(0)
            try:
                parts = re.split(r'[/-]', f)
                if len(parts[0]) == 4:
                    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                else:
                    return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
            except:
                pass
    return datetime.now().strftime("%Y-%m-%d")


# =============================================
# FUNCIONES DE STORAGE (PDFs en Supabase)
# =============================================

def subir_pdf_storage(doc_id: str, pdf_bytes: bytes) -> str:
    """Sube el PDF a Supabase Storage y devuelve el path."""
    path = f"{doc_id}.pdf"
    supabase.storage.from_(BUCKET).upload(
        path,
        pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"}
    )
    return path

def descargar_pdf_storage(storage_path: str) -> bytes:
    """Descarga el PDF desde Supabase Storage."""
    res = supabase.storage.from_(BUCKET).download(storage_path)
    return res

def eliminar_pdf_storage(storage_path: str):
    """Elimina el PDF del bucket."""
    try:
        supabase.storage.from_(BUCKET).remove([storage_path])
    except:
        pass


# =============================================
# FUNCIONES DE BASE DE DATOS (Supabase PostgreSQL)
# =============================================

def insertar_documento(doc_id, tipo, numero, fecha_iso, proveedor, contenido, nombre_archivo, storage_path, paginas_json):
    supabase.table("documentos").upsert({
        "id": doc_id,
        "tipo": tipo,
        "numero": numero,
        "fecha_iso": fecha_iso,
        "proveedor": proveedor,
        "contenido": contenido,
        "nombre_archivo": nombre_archivo,
        "storage_path": storage_path,
        "paginas_json": paginas_json
    }).execute()

def actualizar_documento(doc_id, tipo, nombre_archivo, fecha_iso):
    supabase.table("documentos").update({
        "tipo": tipo,
        "nombre_archivo": nombre_archivo,
        "fecha_iso": fecha_iso
    }).eq("id", doc_id).execute()

def eliminar_documento(doc_id, storage_path):
    supabase.table("documentos").delete().eq("id", doc_id).execute()
    eliminar_pdf_storage(storage_path)

def ejecutar_busqueda(queries):
    """Busca en el campo contenido (ilike para cada término) y devuelve lista de filas."""
    # Construimos filtros OR manualmente: traemos todos y filtramos en memoria
    # para mantener compatibilidad con el plan gratuito de Supabase
    res = supabase.table("documentos").select(
        "id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, storage_path, contenido"
    ).order("fecha_iso", desc=True).execute()

    rows = res.data or []
    resultados = []
    for r in rows:
        contenido = (r.get("contenido") or "").upper()
        if any(q.upper() in contenido for q in queries):
            resultados.append((
                r["id"], r["tipo"], r["numero"], r["fecha_iso"],
                r["nombre_archivo"], r["paginas_json"], r["storage_path"], contenido
            ))
    return resultados

def obtener_todos_documentos(tipo_filtro=None, order_desc=True):
    """Obtiene todos los documentos con filtro opcional de tipo."""
    query = supabase.table("documentos").select(
        "id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, storage_path"
    )
    if tipo_filtro and tipo_filtro != "Todos":
        query = query.eq("tipo", tipo_filtro)
    order = "desc" if order_desc else "asc"
    res = query.order("fecha_iso", desc=order_desc).execute()
    rows = res.data or []
    return [
        (r["id"], r["tipo"], r["numero"], r["fecha_iso"],
         r["nombre_archivo"], r["paginas_json"], r["storage_path"])
        for r in rows
    ]

def obtener_docs_rango_fecha(desde_str, hasta_str, tipo_filtro=None):
    query = supabase.table("documentos").select(
        "id, tipo, fecha_iso, nombre_archivo, storage_path"
    ).gte("fecha_iso", desde_str).lte("fecha_iso", hasta_str).order("fecha_iso")
    if tipo_filtro and tipo_filtro != "Todos":
        query = query.eq("tipo", tipo_filtro)
    res = query.execute()
    rows = res.data or []
    return [(r["id"], r["tipo"], r["fecha_iso"], r["nombre_archivo"], r["storage_path"]) for r in rows]


# =============================================
# ZIP (descarga de PDFs desde Storage)
# =============================================

def generar_zip_blob(resultados, usar_resaltado=False, queries=[]):
    """
    resultados: lista de tuplas donde el índice 6 es storage_path.
    Descarga cada PDF desde Supabase Storage y arma el ZIP.
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for r in resultados:
            nombre = r[4] if r[4].lower().endswith(".pdf") else f"{r[4]}.pdf"
            storage_path = r[6]
            try:
                blob = descargar_pdf_storage(storage_path)
                if usar_resaltado and queries:
                    blob = resaltar_pdf_multiple(blob, queries)
                zf.writestr(nombre, blob)
            except:
                pass
    return buf.getvalue()


# =============================================
# COMPONENTES DE BRANDING
# =============================================

def render_company_header():
    nombre = ""
    logo_blob = None
    try:
        nombre = obtener_config("nombre_empresa") or ""
        if isinstance(nombre, bytes):
            nombre = nombre.decode("utf-8")
    except:
        pass
    try:
        logo_blob = obtener_config("logo_empresa")
        if isinstance(logo_blob, str):
            logo_blob = None
    except:
        pass

    if not nombre and not logo_blob:
        return

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
    nombre = ""
    logo_blob = None
    try:
        nombre = obtener_config("nombre_empresa") or ""
        if isinstance(nombre, bytes):
            nombre = nombre.decode("utf-8")
    except:
        pass
    try:
        logo_blob = obtener_config("logo_empresa")
        if isinstance(logo_blob, str):
            logo_blob = None
    except:
        pass

    total, mapa = obtener_contadores()

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


# =============================================
# EDITOR DE DOCUMENTO
# =============================================

def render_editor_documento(r, search_terms=[], es_inventario=False):
    doc_id, tipo, num, fecha_iso, nombre, pags, storage_path = r
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

        # Descargar PDF desde Storage
        try:
            blob = descargar_pdf_storage(storage_path)
        except:
            st.error("No se pudo cargar el PDF desde el almacenamiento.")
            return

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

        try:
            f_dt = datetime.strptime(fecha_iso, "%Y-%m-%d").date()
        except:
            f_dt = datetime.now().date()
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
                eliminar_documento(doc_id, storage_path)
                del st.session_state[f"confirm_del_{doc_id}"]
                st.rerun()
            if cc2.button("❌ Cancelar", key=f"c_no_{doc_id}"):
                del st.session_state[f"confirm_del_{doc_id}"]
                st.rerun()

        if cb2.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
            actualizar_documento(doc_id, edit_tipo, edit_nombre, edit_fecha.strftime("%Y-%m-%d"))
            st.success("¡Documento actualizado!")
            st.rerun()


# =============================================
# APLICACIÓN PRINCIPAL — SESSION STATE
# =============================================

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

    nombre_actual_raw = obtener_config("nombre_empresa")
    nombre_actual = ""
    if nombre_actual_raw:
        nombre_actual = nombre_actual_raw.decode("utf-8") if isinstance(nombre_actual_raw, bytes) else nombre_actual_raw

    logo_actual_raw = obtener_config("logo_empresa")
    logo_actual = logo_actual_raw if isinstance(logo_actual_raw, bytes) else None

    col_p1, col_p2 = st.columns([2, 1])

    with col_p1:
        st.subheader("🏢 Datos de la Empresa")
        nuevo_nombre = st.text_input("Nombre de la empresa", value=nombre_actual, placeholder="Ej: Cronosol S.A.S.")

        st.subheader("🖼️ Logo de la Empresa")
        st.caption("Formatos aceptados: PNG, JPG, JPEG. Recomendado: imagen cuadrada, mínimo 128×128 px.")
        logo_file = st.file_uploader("Subir logo", type=["png", "jpg", "jpeg"], label_visibility="collapsed")

        st.divider()
        if st.button("💾 Guardar Configuración", key="btn_guardar_config", use_container_width=True):
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

        if logo_actual:
            if st.button("🗑️ Eliminar logo actual", key="btn_eliminar_logo", use_container_width=True):
                supabase.table("config_empresa").delete().eq("clave", "logo_empresa").execute()
                st.rerun()

    with col_p2:
        st.subheader("👁️ Vista Previa")
        preview_nombre = nuevo_nombre.strip() if nuevo_nombre.strip() else (nombre_actual or "Mi Empresa")

        logo_preview = None
        if logo_file:
            logo_file.seek(0)
            logo_preview = logo_file.read()

        if logo_preview:
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

    analizar_clicked = st.button("⚡ Analizar Documentos", key="btn_analizar")
    if analizar_clicked:
        MAX_MB = 50
        MAX_BYTES = MAX_MB * 1024 * 1024
        archivos_validos = []
        for f in archivos:
            if f.size > MAX_BYTES:
                st.error(f"❌ **{f.name}** supera el límite de {MAX_MB} MB ({f.size / 1024 / 1024:.1f} MB). No será procesado.")
            else:
                archivos_validos.append(f)

        st.session_state.pendientes = []
        for f in archivos_validos:
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
                    try:
                        f_val = datetime.strptime(d['fecha'], "%Y-%m-%d").date()
                    except:
                        f_val = datetime.now().date()
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
                cancel_ocr_clicked = st.button("❌ Cancelar Carga", key="cancel_ocr")
                if cancel_ocr_clicked:
                    st.session_state.pendientes = []
                    st.session_state.uploader_id += 1
                    st.rerun()
            with btn_col2:
                quitar_clicked = st.button("🗑️ Quitar archivos con error", key="btn_quitar_error")
                if quitar_clicked:
                    st.session_state.pendientes = [d for d in st.session_state.pendientes if d['ocr']]
                    st.rerun()
        else:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                cancel_ok_clicked = st.button("❌ Cancelar Carga", key="cancel_ok")
                if cancel_ok_clicked:
                    st.session_state.pendientes = []
                    st.session_state.uploader_id += 1
                    st.rerun()
            with btn_col2:
                confirmar_clicked = st.button("🚀 Confirmar y Guardar todo", key="btn_confirmar")
                if confirmar_clicked:
                    errores = []
                    for doc in docs_finales:
                        full_t = ""
                        p_map = {}
                        with fitz.open(stream=doc['blob'], filetype="pdf") as pdf:
                            for idx, p in enumerate(pdf):
                                t = p.get_text().upper()
                                full_t += t + " "
                                p_map[idx + 1] = t
                        try:
                            storage_path = subir_pdf_storage(doc['id'], doc['blob'])
                            insertar_documento(
                                doc['id'], doc['tipo'], "GENERAL", doc['fecha'],
                                "PROVEEDOR", full_t, doc['nombre'],
                                storage_path, json.dumps(p_map)
                            )
                        except Exception as e:
                            errores.append(f"{doc['nombre']}: {e}")

                    if errores:
                        st.error("Algunos documentos no se pudieron guardar:\n" + "\n".join(errores))
                    else:
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
    f_nombre = st.text_input("🔎 Buscar por nombre de archivo", placeholder="Ej: KINO, HENESYS, FVX30432...", key="inv_nombre_search")

    # Reset página al cambiar filtros
    filtro_key = f"{f_tipo}_{f_order}_{f_nombre}"
    if 'inv_filtro_key' not in st.session_state or st.session_state.inv_filtro_key != filtro_key:
        st.session_state.inv_page = 0
        st.session_state.inv_filtro_key = filtro_key

    order_desc = f_order == "Más recientes primero"
    INV_POR_PAGINA = 100

    docs_todos = obtener_todos_documentos(f_tipo, order_desc)

    # Filtrar por nombre en memoria
    if f_nombre.strip():
        docs_todos = [r for r in docs_todos if f_nombre.strip().upper() in r[4].upper()]
    total_inv = len(docs_todos)

    if docs_todos:
        st.markdown('<div class="zip-download-container">', unsafe_allow_html=True)
        label_zip = f"Descargar {f_tipo}" if f_tipo != "Todos" else "Descargar Todo el Inventario"
        st.write(f"📦 **Acciones para {total_inv} documentos encontrados:**")
        if st.button(f"📥 Generar {label_zip} (.zip)"):
            with st.spinner("Generando ZIP, esto puede tomar unos segundos..."):
                zip_data = generar_zip_blob(docs_todos)
            st.download_button(f"⬇️ Descargar ZIP", zip_data, f"{f_tipo.lower().replace(' ','_')}.zip")
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
        st.error("**Zona de riesgo.** Esta acción es irreversible. Los documentos eliminados no se pueden recuperar.")
        st.divider()

        st.markdown("**Paso 1 — Definir filtros**")
        dep_col1, dep_col2, dep_col3 = st.columns(3)
        dep_desde = dep_col1.date_input("Desde", value=datetime(2020, 1, 1).date(), key="dep_desde")
        dep_hasta = dep_col2.date_input("Hasta", value=datetime.now().date(), key="dep_hasta")
        dep_tipo = dep_col3.selectbox("Tipo de documento", ["Todos", "Factura de Compra", "Manifiesto de Aduana"], key="dep_tipo")

        if dep_desde > dep_hasta:
            st.error("La fecha 'Desde' no puede ser posterior a la fecha 'Hasta'.")
        else:
            desde_str = dep_desde.strftime("%Y-%m-%d")
            hasta_str = dep_hasta.strftime("%Y-%m-%d")
            docs_a_eliminar = obtener_docs_rango_fecha(desde_str, hasta_str, dep_tipo)

            if not docs_a_eliminar:
                st.info("Ningún documento coincide con los filtros seleccionados.")
            else:
                st.markdown(f"**Paso 2 — Preview:** Se eliminarían **{len(docs_a_eliminar)} documento(s)**")

                with st.expander(f"Ver los {len(docs_a_eliminar)} documento(s) que serán eliminados"):
                    for d in docs_a_eliminar:
                        fecha_v = datetime.strptime(d[2], "%Y-%m-%d").strftime("%d/%m/%Y")
                        st.markdown(f"- `{fecha_v}` · {d[1]} · **{d[3]}**")

                st.divider()
                st.markdown("**Paso 3 — Confirmación**")
                st.markdown("Para ejecutar la eliminación, escribe exactamente: <span style='color:#dc3545;font-weight:700;font-family:monospace;'>CONFIRMAR ELIMINACIÓN</span>", unsafe_allow_html=True)
                frase = st.text_input("Frase de confirmación", key="dep_frase", placeholder="CONFIRMAR ELIMINACIÓN")

                if frase == "CONFIRMAR ELIMINACIÓN":
                    if st.button("🗑️ Ejecutar eliminación masiva", key="dep_ejecutar"):
                        for d in docs_a_eliminar:
                            eliminar_documento(d[0], d[4])
                        st.success(f"✅ {len(docs_a_eliminar)} documento(s) eliminado(s) correctamente.")
                        st.rerun()
                elif frase:
                    st.error("La frase no coincide. Verifica mayúsculas y tildes.")


# =============================================
# MÓDULO: BUSCADOR
# =============================================

elif choice == "🔍 Buscador":
    render_company_header()
    st.header("Buscador Inteligente Multitermino")
    query_in = st.text_input("Ingrese Referencias (sepárelas por coma)").upper()

    if query_in:
        queries = [q.strip() for q in query_in.split(",") if q.strip()]

        if query_in != st.session_state.last_query:
            st.session_state.search_results = ejecutar_busqueda(queries)
            st.session_state.last_query = query_in
            st.session_state.search_page = 0

        res_completo = st.session_state.search_results

        if res_completo:
            st.write("**Filtrar por tipo:**")
            sw1, sw2, _ = st.columns([1.4, 1.8, 3])
            with sw1:
                mostrar_facturas = st.toggle("Facturas de Compra", value=True, key="sw_facturas")
            with sw2:
                mostrar_manifiestos = st.toggle("Manifiestos de Aduana", value=True, key="sw_manifiestos")

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

                st.markdown('<div class="zip-download-container">', unsafe_allow_html=True)
                st.write(f"📂 **{total_resultados} resultado(s){label_filtro}** — Mostrando {inicio+1}–{min(fin, total_resultados)}")
                cb1, cb2 = st.columns(2)
                with cb1:
                    if st.button("📥 Descargar Resultados Subrayados (.zip)", use_container_width=True):
                        with st.spinner("Generando ZIP resaltado..."):
                            zip_res = generar_zip_blob(res, True, queries)
                        st.download_button("⬇️ Descargar subrayados", zip_res, "busqueda_resaltada.zip")
                with cb2:
                    if st.button("📥 Descargar Resultados Originales (.zip)", use_container_width=True):
                        with st.spinner("Generando ZIP original..."):
                            zip_orig = generar_zip_blob(res, False)
                        st.download_button("⬇️ Descargar originales", zip_orig, "busqueda_original.zip")
                st.markdown('</div>', unsafe_allow_html=True)

                for r in res_pagina:
                    coinciden = [q for q in queries if q in r[7]]
                    fecha_v = datetime.strptime(r[3], "%Y-%m-%d").strftime("%d/%m/%Y")
                    tipo_emoji = "🟢" if r[1] == "Factura de Compra" else "🔵"
                    with st.expander(f"{tipo_emoji} {fecha_v} | {r[4]} (Coincide con: {', '.join(coinciden)})"):
                        render_editor_documento(r[:7], queries, es_inventario=False)

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
