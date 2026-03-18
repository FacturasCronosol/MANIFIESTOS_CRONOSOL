import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64
import json
import re
import os
from datetime import datetime

# Configuración profesional
st.set_page_config(page_title="Gestión Cronosol - DIAN", layout="wide", page_icon="🛡️")

# Estilo personalizado
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; background-color: #007bff; color: white; font-weight: bold; }
    .stDownloadButton>button { background-color: #28a745 !important; color: white !important; }
    /* Estilo para botón de eliminar (Rojo) */
    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] .stButton button[key*="del_"] {
        background-color: #dc3545 !important;
        color: white !important;
    }
    div[data-testid="stVerticalBlock"] div[data-testid="stHorizontalBlock"] .stButton button[key*="confirm_del_"] {
        background-color: #c82333 !important;
        color: white !important;
    }
    .highlight-page { background-color: #fff3cd; padding: 5px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .ocr-warning { background-color: #f8d7da; color: #721c24; padding: 10px; border-radius: 5px; border-left: 5px solid #dc3545; font-weight: bold; margin-top: 5px; }
    .cancel-btn button { background-color: #6c757d !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# Diccionario para meses cortos y largos
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
    
    try:
        c.execute("SELECT fecha_iso FROM documentos LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("DROP TABLE IF EXISTS documentos")
    
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

def resaltar_pdf(pdf_bytes, query):
    if not query:
        return pdf_bytes
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text_instances = page.search_for(query)
            for inst in text_instances:
                annot = page.add_highlight_annot(inst)
                annot.update()
        output_bytes = doc.write()
        doc.close()
        return output_bytes
    except Exception as e:
        st.error(f"Error al resaltar: {e}")
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
    
    # Limpieza profunda de caracteres no deseados
    texto_fecha = texto_fecha.upper().replace("DE ", " ").replace(".", "").replace(",", "").strip()
    texto_fecha = re.sub(r'[^A-Z0-9/\-\s]', '', texto_fecha) # Solo dejamos letras, números y separadores
    texto_fecha = re.sub(r'\s+', ' ', texto_fecha)
    
    # Intento 1: Formatos numéricos (DD/MM/AAAA o AAAA/MM/DD)
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

    # Intento 2: Fechas con nombre de mes (Ej: 15 ENERO 2024)
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
    
    # Intento 1: Buscar etiquetas específicas (Facturas y Manifiestos)
    palabras_clave = [
        r'FECHA EMISION', r'FECHA DE EMISIÓN', r'FECHA DE FACTURA', 
        r'FECHA DOCUMENTO', r'FECHA EXPEDICION', r'FECHA:', r'F\. EMISION'
    ]
    
    for p in palabras_clave:
        match = re.search(f'{p}\s*[:\-]?\s*(.{{1,30}})', texto_limpio, re.DOTALL)
        if match:
            posible_fecha = match.group(1).strip()
            # Buscar estructura de fecha dentro del pedazo encontrado
            f_num = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})|(\d{4}[/-]\d{1,2}[/-]\d{1,2})', posible_fecha)
            if f_num: return normalizar_fecha_a_iso(f_num.group(0))
            
            f_txt = re.search(r'(\d{1,2}\s+[A-Z]{3,10}\s+\d{4})', posible_fecha)
            if f_txt: return normalizar_fecha_a_iso(f_txt.group(0))

    # Intento 2: Búsqueda global
    patrones_globales = [
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',  # DD/MM/AAAA
        r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',  # AAAA/MM/DD
        r'(\d{1,2}\s+[A-Z]{3,10}\s+\d{4})' # DD MES AAAA
    ]
    
    for pat in patrones_globales:
        match_global = re.search(pat, texto_limpio)
        if match_global:
            return normalizar_fecha_a_iso(match_global.group(0))
                
    return datetime.now().strftime("%Y-%m-%d")

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
    ">📄 Ver PDF Resaltado (Pág. {page_num})</button>
    """
    return js

# --- INTERFAZ ---
if 'pendientes' not in st.session_state:
    st.session_state.pendientes = []

# ID para refrescar el uploader (técnica del Key-swapping)
if 'uploader_id' not in st.session_state:
    st.session_state.uploader_id = 0

def limpiar_carga_total():
    st.session_state.pendientes = []
    st.session_state.uploader_id += 1 # Al cambiar la key, el uploader se vacía

with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Menú", ["🔍 Buscador", "📤 Carga Masiva"])
    st.divider()
    st.info("Orden cronológico (Nuevo → Viejo).")

if choice == "📤 Carga Masiva":
    st.header("Carga Masiva de Documentos")
    
    tipo_doc = st.radio("Tipo de Documento:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    
    # El uploader usa una key dinámica para que podamos forzar su limpieza
    archivos = st.file_uploader(
        "Subir archivos PDF", 
        type="pdf", 
        accept_multiple_files=True, 
        key=f"uploader_{st.session_state.uploader_id}"
    )

    # Si no hay archivos en el uploader pero hay pendientes (se presionó la X individual o se borraron manualmente)
    if not archivos and st.session_state.pendientes:
        st.session_state.pendientes = []
        st.rerun()

    if archivos:
        if st.button("⚡ Analizar Documentos"):
            st.session_state.pendientes = []
            for f in archivos:
                f.seek(0)
                pdf_bytes = f.read()
                doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    if len(doc) > 0:
                        raw_text = doc[0].get_text()
                        tiene_ocr = len(raw_text.strip()) > 50
                        fecha_iso = extraer_fecha_texto(raw_text)
                        st.session_state.pendientes.append({
                            "id": doc_id, "nombre": f.name, "tipo": tipo_doc,
                            "fecha_iso": fecha_iso, "blob": pdf_bytes,
                            "ocr_warning": not tiene_ocr
                        })

        if st.session_state.pendientes:
            st.subheader("📋 Revisión de Datos")
            
            st.markdown('<div class="cancel-btn">', unsafe_allow_html=True)
            if st.button("❌ Cancelar y Limpiar Todo"):
                limpiar_carga_total()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
            
            documentos_finales = []
            for i, d in enumerate(st.session_state.pendientes):
                with st.container():
                    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        f_input = st.text_input(f"Fecha (AAAA-MM-DD)", value=d['fecha_iso'], key=f"f_{i}")
                    with col2:
                        st.write(f"📄 **{d['nombre']}**")
                        if d.get("ocr_warning"):
                            st.markdown('<div class="ocr-warning">⚠️ Este PDF parece no tener OCR (no se detectó texto).</div>', unsafe_allow_html=True)
                    
                    documentos_finales.append({**d, "fecha_iso": normalizar_fecha_a_iso(f_input)})
                    st.markdown('</div>', unsafe_allow_html=True)

            if st.button("🚀 Guardar en Base de Datos"):
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
                        c.execute("""INSERT INTO documentos 
                                   (id, tipo, numero, fecha_iso, proveedor, contenido, nombre_archivo, pdf_blob, paginas_json) 
                                   VALUES (?,?,?,?,?,?,?,?,?)""", 
                                 (doc['id'], doc['tipo'], doc['nombre'], doc['fecha_iso'], 
                                  "GENERAL", texto_full, doc['nombre'], doc['blob'], json.dumps(dict_pags)))
                        conn.commit()
                    except sqlite3.IntegrityError:
                        pass
                    bar.progress((idx + 1) / len(documentos_finales))
                
                st.success("¡Documentos indexados correctamente!")
                limpiar_carga_total()
                st.rerun()

elif choice == "🔍 Buscador":
    # Limpiar cualquier residuo de carga al cambiar al buscador
    if st.session_state.pendientes or st.session_state.uploader_id > 0:
        st.session_state.pendientes = []
        # No reiniciamos el uploader_id aquí para no causar bucles, solo la lista
        
    st.header("Buscador de Trazabilidad")
    query = st.text_input("Ingrese Referencia, Contenedor o Palabra Clave").upper()

    if query:
        try:
            c.execute("""SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob 
                         FROM documentos WHERE contenido LIKE ? ORDER BY fecha_iso DESC""", (f'%{query}%',))
            res = c.fetchall()
            
            if res:
                st.write(f"Resultados encontrados: **{len(res)}**")
                for r in res:
                    doc_id, tipo, num, fecha_iso, nombre, pags, blob = r
                    emoji = "🟢" if tipo == "Factura de Compra" else "🔵"
                    fecha_vis = formatear_fecha_visual(fecha_iso)
                    
                    with st.expander(f"{emoji} {fecha_vis} | {tipo} - {nombre}"):
                        tab1, tab2 = st.tabs(["📄 Ver / Descargar", "⚙️ Gestionar"])
                        
                        with tab1:
                            encontrado = []
                            if pags:
                                p_dict = json.loads(pags)
                                encontrado = [p for p, cont in p_dict.items() if query in cont]
                            
                            col_i, col_b = st.columns([2, 1])
                            with col_i:
                                if encontrado:
                                    st.markdown(f'<div class="highlight-page">📍 Página(s): {", ".join(map(str, encontrado))}</div>', unsafe_allow_html=True)
                                else:
                                    st.info("Referencia encontrada en el contenido general.")
                            with col_b:
                                p_dest = encontrado[0] if encontrado else 1
                                pdf_resaltado = resaltar_pdf(blob, query)
                                st.components.v1.html(abrir_pdf_js(pdf_resaltado, p_dest), height=70)
                                st.download_button("💾 Bajar PDF", pdf_resaltado, f"RESALTADO_{nombre}", "application/pdf", key=f"d_{doc_id}")
                        
                        with tab2:
                            st.subheader("Editar información")
                            edit_nombre = st.text_input("Nombre del archivo", value=nombre, key=f"n_{doc_id}")
                            col_e1, col_e2 = st.columns(2)
                            edit_tipo = col_e1.selectbox("Tipo", ["Factura de Compra", "Manifiesto de Aduana"], 
                                                       index=0 if tipo=="Factura de Compra" else 1, key=f"t_{doc_id}")
                            edit_fecha = col_e2.text_input("Fecha (AAAA-MM-DD)", value=fecha_iso, key=f"f_edit_{doc_id}")
                            
                            st.divider()
                            col_btn1, col_btn2 = st.columns(2)
                            
                            if col_btn1.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
                                actualizar_documento(doc_id, edit_tipo, edit_nombre, edit_fecha)
                                st.success("¡Datos actualizados!")
                                st.rerun()
                            
                            if f"confirm_del_{doc_id}" not in st.session_state:
                                if col_btn2.button("🗑️ Eliminar Documento", key=f"del_{doc_id}"):
                                    st.session_state[f"confirm_del_{doc_id}"] = True
                                    st.rerun()
                            else:
                                st.error("¿Estás seguro de eliminar este documento?")
                                col_c1, col_c2 = st.columns(2)
                                if col_c1.button("✅ Sí, eliminar definitivamente", key=f"confirm_del_btn_{doc_id}"):
                                    eliminar_documento(doc_id)
                                    del st.session_state[f"confirm_del_{doc_id}"]
                                    st.rerun()
                                if col_c2.button("❌ Cancelar", key=f"cancel_del_{doc_id}"):
                                    del st.session_state[f"confirm_del_{doc_id}"]
                                    st.rerun()
            else:
                st.error("No se encontraron resultados.")
        except sqlite3.OperationalError as e:
            st.error(f"Error técnico: {e}")
