import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib
import base64

# Configuración profesional para visualización en PC y Móvil
st.set_page_config(page_title="Gestión Cronosol - DIAN", layout="wide", page_icon="🛡️")

# Estilo personalizado para botones y optimización de UI
st.markdown("""
    <style>
    .stButton>button { 
        width: 100%; 
        border-radius: 8px; 
        height: 3.5em; 
        background-color: #007bff; 
        color: white; 
        font-weight: bold;
    }
    /* Estilo para el botón de apertura de PDF */
    .stDownloadButton>button {
        background-color: #28a745 !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Inicialización de la base de datos
conn = sqlite3.connect('gestion_cronosol.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS documentos 
             (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha TEXT, 
              proveedor TEXT, contenido TEXT, nombre_archivo TEXT, pdf_blob BLOB)''')
conn.commit()

# Función para abrir PDF en pestaña nueva usando JavaScript (Solución definitiva a pestaña vacía)
def abrir_pdf_js(bin_file, file_name):
    base64_pdf = base64.b64encode(bin_file).decode('utf-8')
    # Script para crear un Blob en el cliente y abrirlo sin restricciones de data-url
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
        window.open(fileURL, '_blank');
    }}
    </script>
    <button onclick="openPDF()" style="
        width: 100%;
        padding: 0.75em 1.5em;
        background-color: #28a745;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: bold;
        cursor: pointer;
        margin-top: 10px;
        margin-bottom: 10px;
    ">📄 Visualizar PDF (Pestaña Nueva)</button>
    """
    return js

# --- MENÚ LATERAL ---
with st.sidebar:
    st.title("🛡️ Cronosol")
    choice = st.radio("Menú de Operaciones", ["🔍 Buscador Rápido", "📤 Cargar Documentos"])
    st.divider()
    st.info("Utilice el buscador para localizar referencias en facturas y manifiestos de aduana.")

# --- MÓDULO DE CARGA ---
if choice == "📤 Cargar Documentos":
    st.header("Registro de Nuevos Documentos")
    
    with st.form("form_carga", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tipo = st.selectbox("Tipo de Documento", ["Factura de Compra", "Manifiesto de Aduana"])
            numero = st.text_input("Número del Documento (ID)")
        with col2:
            proveedor = st.text_input("Proveedor / Importador")
            fecha = st.date_input("Fecha de Emisión")
            
        archivo = st.file_uploader("Subir archivo PDF", type="pdf")
        submit = st.form_submit_button("Guardar en Base de Datos")

        if submit:
            if archivo and numero and proveedor:
                pdf_bytes = archivo.read()
                doc_id = hashlib.sha256(pdf_bytes).hexdigest()
                
                c.execute("SELECT numero FROM documentos WHERE id=?", (doc_id,))
                if c.fetchone():
                    st.error("⚠️ Este documento ya existe en el sistema.")
                else:
                    with st.spinner("Indexando contenido..."):
                        texto = ""
                        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                            for pagina in doc:
                                texto += pagina.get_text()
                        
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?,?,?)", 
                                  (doc_id, tipo, numero, str(fecha), proveedor.upper(), texto.upper(), archivo.name, pdf_bytes))
                        conn.commit()
                        st.success(f"✅ {tipo} guardado con éxito.")
            else:
                st.warning("Por favor complete todos los campos obligatorios.")

# --- MÓDULO DE BÚSQUEDA ---
elif choice == "🔍 Buscador Rápido":
    st.header("Consulta de Trazabilidad")
    query = st.text_input("Ingrese Referencia o Palabra Clave").upper()

    if query:
        # Búsqueda global
        df = pd.read_sql_query(f"SELECT id, tipo, numero, fecha, proveedor, nombre_archivo FROM documentos WHERE contenido LIKE '%{query}%' ORDER BY fecha DESC", conn)
        
        if not df.empty:
            st.write(f"Se encontraron **{len(df)}** registros para: `{query}`")
            
            for index, row in df.iterrows():
                with st.expander(f"📌 {row['tipo']}: {row['numero']} - {row['proveedor']}"):
                    col_info, col_btn = st.columns([2, 1])
                    
                    with col_info:
                        st.write(f"**Fecha:** {row['fecha']}")
                        st.write(f"**Archivo Original:** {row['nombre_archivo']}")
                    
                    with col_btn:
                        c.execute("SELECT pdf_blob FROM documentos WHERE id=?", (row['id'],))
                        blob = c.fetchone()[0]
                        
                        # Botón con JavaScript para apertura limpia en pestaña nueva
                        st.components.v1.html(abrir_pdf_js(blob, row['nombre_archivo']), height=70)
                        
                        # Botón de descarga física (siempre necesario como respaldo)
                        st.download_button(
                            label="💾 Descargar copia local",
                            data=blob,
                            file_name=row['nombre_archivo'],
                            mime="application/pdf",
                            key=f"dl_{row['id']}"
                        )
        else:
            st.error(f"No se encontraron documentos con la referencia '{query}'.")
