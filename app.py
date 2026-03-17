import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64

# Configuración profesional
st.set_page_config(page_title="Gestión Cronosol - DIAN", layout="wide", page_icon="🛡️")

# Estilo personalizado
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

# Base de datos
conn = sqlite3.connect('gestion_cronosol.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS documentos 
             (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha TEXT, 
              proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB)''')
conn.commit()

def mostrar_pdf(bin_file):
    base64_pdf = base64.b64encode(bin_file).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Cronosol Legalidad")
    choice = st.radio("Acciones", ["🔍 Buscador de Referencias", "📤 Cargar Documentos"])
    st.info("Sistema de trazabilidad para inspecciones DIAN.")

# --- MÓDULO DE CARGA ---
if choice == "📤 Cargar Documentos":
    st.header("Registro de Nueva Mercancía")
    col1, col2 = st.columns(2)
    with col1:
        tipo = st.selectbox("Documento", ["Factura de Compra", "Manifiesto de Aduana"])
        numero = st.text_input(f"Número de {tipo}")
    with col2:
        proveedor = st.text_input("Nombre del Proveedor / Importador")
        fecha = st.date_input("Fecha del Documento")

    archivo = st.file_uploader("Subir PDF Original", type="pdf")

    if st.button("Guardar en el Historial"):
        if archivo and numero and proveedor:
            pdf_bytes = archivo.read()
            doc_id = hashlib.sha256(pdf_bytes).hexdigest()
            c.execute("SELECT numero FROM documentos WHERE id=?", (doc_id,))
            if c.fetchone():
                st.error("⚠️ Este archivo ya fue cargado previamente.")
            else:
                texto = ""
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    for pagina in doc: texto += pagina.get_text()
                c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?)", 
                          (doc_id, tipo, numero, str(fecha), proveedor.upper(), texto.upper(), archivo.name, pdf_bytes))
                conn.commit()
                st.success(f"✅ {tipo} guardado correctamente.")

# --- MÓDULO DE BÚSQUEDA ---
elif choice == "🔍 Buscador de Referencias":
    st.header("Consulta Instantánea")
    query = st.text_input("Ingresa la referencia (ej: NF7125)").upper()

    if query:
        df = pd.read_sql_query(f"SELECT id, tipo, numero, fecha, proveedor, nombre_archivo FROM documentos WHERE contenido LIKE '%{query}%' ORDER BY fecha DESC", conn)
        
        if not df.empty:
            st.write(f"Resultados para: **{query}**")
            seleccion = st.selectbox("Selecciona un documento:", df['id'], 
                                     format_func=lambda x: f"{df[df['id']==x]['tipo'].values[0]} - {df[df['id']==x]['numero'].values[0]}")
            
            col_a, col_b = st.columns([1, 2])
            with col_a:
                doc_data = df[df['id'] == seleccion].iloc[0]
                st.write(f"**Tipo:** {doc_data['tipo']}")
                st.write(f"**Número:** {doc_data['numero']}")
                st.write(f"**Proveedor:** {doc_data['proveedor']}")
                
                # Botón de descarga para evitar el bloqueo de Brave
                c.execute("SELECT pdf_blob FROM documentos WHERE id=?", (seleccion,))
                blob = c.fetchone()[0]
                st.download_button(label="📥 Descargar PDF para Ver/Imprimir", data=blob, file_name=doc_data['nombre_archivo'], mime="application/pdf")
            
            with col_b:
                mostrar_pdf(blob)
        else:
            st.error(f"No se encontró la referencia '{query}'.")
