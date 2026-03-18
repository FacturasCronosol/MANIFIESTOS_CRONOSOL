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
    .highlight-page { background-color: #fff3cd; padding: 5px; border-radius: 5px; border-left: 5px solid #ffc107; font-weight: bold; margin-bottom: 10px; }
    .upload-card { border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# Diccionario para meses cortos
MESES_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"
}

# Inicialización de la base de datos
def init_db():
    db_path = 'gestion_cronosol_v4.db' 
    conn = sqlite3.connect(db_path, check_same_thread=False)
    c = conn.cursor()
    
    # Verificación de esquema para evitar errores de columnas faltantes
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
    texto_fecha = texto_fecha.upper().replace("DE ", "").replace(".", "").replace(",", "").strip()
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
    if re.match(r'^\d{4}-\d{2}-\d{2}$', texto_fecha):
        return texto_fecha
    return datetime.now().strftime("%Y-%m-%d")

def extraer_fecha_texto(texto):
    prioridades = [r'FECHA EMISION', r'FECHA DE EMISIÓN', r'FECHA DE FACTURA', r'FECHA:']
    for p in prioridades:
        match = re.search(f'{p}.*?(\\d{{1,2}}[/-]\\d{{1,2}}[/-]\\d{{4}})', texto, re.IGNORECASE | re.DOTALL)
        if match:
            return normalizar_fecha_a_iso(match.group(1))
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
with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Menú", ["🔍 Buscador", "📤 Carga Masiva"])
    st.divider()
    st.info("Orden cronológico (Nuevo → Viejo).")

if choice == "📤 Carga Masiva":
    st.header("Carga Masiva de Documentos")
    tipo_doc = st.radio("Tipo de Documento:", ["Factura de Compra", "Manifiesto de Aduana"], horizontal=True)
    archivos = st.file_uploader("Subir archivos PDF", type="pdf", accept_multiple_files=True)

    if archivos:
        if st.button("⚡ Analizar Documentos"):
            st.session_state.pendientes = []
            for f in archivos:
                f.seek(0)
                pdf_bytes = f.read()
                doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    if len(doc) > 0:
                        fecha_iso = extraer_fecha_texto(doc[0].get_text())
                        st.session_state.pendientes.append({
                            "id": doc_id, "nombre": f.name, "tipo": tipo_doc,
                            "fecha_iso": fecha_iso, "blob": pdf_bytes
                        })

        if 'pendientes' in st.session_state and st.session_state.pendientes:
            st.subheader("📋 Revisión de Datos")
            documentos_finales = []
            for i, d in enumerate(st.session_state.pendientes):
                with st.container():
                    st.markdown('<div class="upload-card">', unsafe_allow_html=True)
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        f_input = st.text_input(f"Fecha (AAAA-MM-DD)", value=d['fecha_iso'], key=f"f_{i}")
                    with col2:
                        st.write(f"📄 **{d['nombre']}**")
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
                st.session_state.pendientes = []
                st.rerun()

elif choice == "🔍 Buscador":
    st.header("Buscador de Trazabilidad")
    query = st.text_input("Ingrese Referencia, Contenedor o Palabra Clave").upper()

    if query:
        try:
            # Aquí se define la variable 'res' tras ejecutar la consulta
            c.execute("""SELECT id, tipo, numero, fecha_iso, nombre_archivo, paginas_json, pdf_blob 
                         FROM documentos WHERE contenido LIKE ? ORDER BY fecha_iso DESC""", (f'%{query}%',))
            res = c.fetchall()
            
            if res:
                st.write(f"Resultados encontrados: **{len(res)}**")
                for r in res:
                    doc_id, tipo, num, fecha_iso, nombre, pags, blob = r
                    # Corregido: Coincidencia exacta con los nombres de la carga
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
                            
                            col_btn1, col_btn2 = st.columns(2)
                            if col_btn1.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
                                actualizar_documento(doc_id, edit_tipo, edit_nombre, edit_fecha)
                                st.success("¡Datos actualizados!")
                                st.rerun()
                            
                            if col_btn2.button("🗑️ Eliminar Documento", key=f"del_{doc_id}"):
                                eliminar_documento(doc_id)
                                st.warning("Documento eliminado correctamente.")
                                st.rerun()
            else:
                st.error("No se encontraron resultados.")
        except sqlite3.OperationalError as e:
            st.error(f"Error técnico: {e}")
