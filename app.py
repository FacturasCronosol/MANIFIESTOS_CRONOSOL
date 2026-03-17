import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64

# Configuración profesional
st.set_page_config(page_title="Gestión Cronosol - DIAN", layout="wide", page_icon="🛡️")

# Estilo personalizado para que se vea mejor en móvil
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stDataFrame { width: 100%; }
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
    # AQUÍ ESTABA EL ERROR: Cambia unsafe_allow_stdio por unsafe_allow_html
    st.markdown(pdf_display, unsafe_allow_html=True)

with col_a:
                # ... (tus códigos actuales de texto) ...
                # Añade esto al final del bloque with col_a:
                st.download_button(
                    label="📥 Descargar PDF para imprimir/ver",
                    data=blob,
                    file_name=doc_data['nombre_archivo'],
                    mime="application/pdf"
                )

# --- MENÚ LATERAL ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/7542/7542670.png", width=100)
    st.title("Cronosol Legalidad")
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
            
            # Verificar duplicado
            c.execute("SELECT numero FROM documentos WHERE id=?", (doc_id,))
            if c.fetchone():
                st.error("⚠️ Error: Este archivo exacto ya fue cargado previamente.")
            else:
                with st.spinner("Indexando contenido para búsquedas rápidas..."):
                    texto = ""
                    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                        for pagina in doc:
                            texto += pagina.get_text()
                    
                    c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?)", 
                              (doc_id, tipo, numero, str(fecha), proveedor.upper(), texto.upper(), archivo.name, pdf_bytes))
                    conn.commit()
                    st.success(f"✅ {tipo} {numero} de {proveedor} guardado correctamente.")
        else:
            st.warning("Por favor, completa todos los campos antes de guardar.")

# --- MÓDULO DE BÚSQUEDA ---
elif choice == "🔍 Buscador de Referencias":
    st.header("Consulta Instantánea")
    query = st.text_input("Ingresa la referencia (ej: NF7125, GAF001, etc.)").upper()

    if query:
        # Buscamos en toda la base de datos
        df = pd.read_sql_query(f"""SELECT id, tipo, numero, fecha, proveedor, nombre_archivo 
                                   FROM documentos 
                                   WHERE contenido LIKE '%{query}%' 
                                   ORDER BY fecha DESC""", conn)
        
        if not df.empty:
            st.write(f"Se encontraron **{len(df)}** documentos relacionados:")
            
            # Selección de documento para ver el PDF
            seleccion = st.selectbox("Selecciona un documento para ver el PDF:", 
                                     df['id'], 
                                     format_func=lambda x: f"{df[df['id']==x]['tipo'].values[0]} - {df[df['id']==x]['numero'].values[0]} ({df[df['id']==x]['proveedor'].values[0]})")
            
            # Mostrar detalles y PDF
            col_a, col_b = st.columns([1, 2])
            
            with col_a:
                doc_data = df[df['id'] == seleccion].iloc[0]
                st.metric("Documento", doc_data['tipo'])
                st.write(f"**Número:** {doc_data['numero']}")
                st.write(f"**Fecha:** {doc_data['fecha']}")
                st.write(f"**Proveedor:** {doc_data['proveedor']}")
            
            with col_b:
                c.execute("SELECT pdf_blob FROM documentos WHERE id=?", (seleccion,))
                blob = c.fetchone()[0]
                mostrar_pdf(blob)
        else:
            st.error(f"No hay registros del artículo '{query}'.")
