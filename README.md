# 🤖 Bot Multiagente – LangGraph (Demo)

Este repositorio contiene una **demo simple de un bot multiagente** construido con **LangGraph**, cuyo objetivo es mostrar cómo:

* Un agente decide cuándo usar herramientas
* Se integran **múltiples proveedores de IA** (Azure OpenAI y OpenAI directo)
* Se pueden generar **artefactos** (ej. imágenes) y exponerlos vía API
* El diseño es **replicable** para otros clientes o casos de uso

> ⚠️ Este bot es deliberadamente **minimalista**.
> El foco está en la **arquitectura y el flujo multiagente**, no en la UI ni en features avanzadas.

---

## 🧠 ¿Qué hace este bot?

El bot puede:

* 💬 Responder de forma conversacional
* 🌤️ Consultar el **clima actual** de una ciudad (tool externa)
* 🖼️ **Generar imágenes** a partir de texto (tool especializada)
* 🗄️ Consultar una **base de datos SQL** usando una tool parametrizable y un CSV de esquema
* 🔀 Decidir automáticamente **qué herramienta usar** según la intención del usuario

Todo esto es orquestado por **LangGraph**, siguiendo el patrón:

```
Usuario → Agente → Tool (si aplica) → Agente → Respuesta final
```

---

## 🏗️ Arquitectura simple

* **LangGraph**: orquestación del flujo agent ↔ tools
* **Azure OpenAI (GPT-4o)**:

  * Razonamiento
  * Conversación
  * Decisión de herramientas
* **OpenAI directo (GPT-4o)**:

  * Generación de imágenes
* **Tool SQL parametrizable**:

  * Usa `database_url` para conectarse a motores SQL compatibles con SQLAlchemy
  * Usa un CSV para describir tablas, columnas y joins sugeridos
  * Genera SQL de solo lectura a partir de preguntas de negocio
* **FastAPI**:

  * Exposición del endpoint `/chat`
  * Servir archivos estáticos (`/static`)
* **Streamlit**:

  * Interfaz de chat simple para demo

---

## 📂 Estructura del proyecto

```
.
├── src/
│   ├── app.py              # API FastAPI
│   ├── graph.py            # Grafo LangGraph
│   ├── prompts/
│   │   └── system.md       # Prompt principal del agente
│   ├── tools/
│   │   ├── weather.py      # Tool: clima (Open-Meteo)
│   │   ├── image.py        # Tool: generación de imágenes (OpenAI)
│   │   └── sql.py          # Tool: consultas SQL con esquema CSV
├── examples/
│   └── sql/
│       ├── company_schema.csv
│       └── create_demo_db.py
├── static/
│   └── generated/          # Imágenes generadas
├── requirements.txt
├── .env.example
└── README.md
```

---

## ⚙️ Variables de entorno

Crea un archivo `.env` a partir de `.env.example`.

### Azure OpenAI (chat y razonamiento)

```env
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o
```

### OpenAI directo (solo imágenes)

```env
OPENAI_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-4o
```

### Exposición pública de archivos

```env
PUBLIC_BASE_URL=http://localhost:8000
```

### SQL estructurado

```env
SQL_DATABASE_URL=sqlite:///./examples/sql/demo.db
SQL_SCHEMA_CSV_PATH=examples/sql/company_schema.csv

# Opcional: usar otro deployment para generar SQL
AZURE_OPENAI_SQL_DEPLOYMENT=gpt-4o
```

La tool SQL espera un CSV con columnas de metadata como estas:

```csv
schema_name,table_name,column_name,column_description,data_type,data_format,related_table,related_column
analytics,orders,customer_id,Cliente que realizó la orden,INTEGER,,customers,customer_id
```

Encabezados equivalentes como `schema`, `table`, `column`, `description` o `tipo_dato` también funcionan.

Si quieres una base local lista para el workshop, puedes crear una SQLite de ejemplo:

```bash
python3 examples/sql/create_demo_db.py
```

---

## ▶️ Cómo ejecutar el bot

### 1️⃣ Crear entorno virtual e instalar dependencias

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2️⃣ Levantar la API

```bash
python -m uvicorn src.app:app --reload --port 8000
```

La API quedará disponible en:

```
http://localhost:8000/chat
```

---

## 🔁 Swagger disponible en
```
http://localhost:8000/docs#/default/chat_chat_post
```

---
## 🔁 Contrato de la API

### Request

```json
POST /chat
{
  "message": "Genera un mapa minimalista de Colombia"
}
```

### Response

```json
{
  "answer": "Markdown con texto e imágenes"
}
```

Las imágenes se devuelven como **URLs absolutas** servidas desde `/static`.

---

## 🧪 Ejemplos de uso

* **Clima**

  > “¿Cómo está el clima en Roma hoy?”

* **Imagen**

  > “Genera un mapa minimalista de Colombia en estilo flat”

* **SQL**

  > “¿Cuáles son los 5 clientes con más órdenes?”

  > “Consulta la base SQL y dime cuántos pedidos cancelados hubo por ciudad”

---

## 🎯 Propósito del repositorio

Este proyecto sirve como:

* 📚 Ejemplo didáctico para charlas técnicas
* 🧩 Plantilla base para nuevos agentes
* 🔁 Artefacto replicable para otros clientes
* 🧠 Referencia de uso real de LangGraph en producción

No pretende ser un producto final ni una solución completa.

---

## 📌 Notas finales

* El comportamiento del agente está gobernado por:

  * `system.md` (prompt)
  * tools registradas con `@tool`
* Agregar una nueva tool implica:

  1. Crear el archivo en `src/tools`
  2. Decorar la función
  3. Importarla en `graph.py`

## 🗄️ Cómo funciona la nueva tool SQL

La tool `query_sql_database` sigue este flujo:

1. Lee la conexión desde `database_url` o desde `SQL_DATABASE_URL`.
2. Lee el esquema desde `schema_csv_path` o desde `SQL_SCHEMA_CSV_PATH`.
3. Resume tablas, columnas y relaciones sugeridas.
4. Genera SQL de solo lectura usando Azure OpenAI.
5. Ejecuta la consulta y devuelve filas serializadas.

Con la SQLite de ejemplo, una configuración mínima funcional queda así:

```env
SQL_DATABASE_URL=sqlite:///./examples/sql/demo.db
SQL_SCHEMA_CSV_PATH=examples/sql/company_schema.csv
```

### Parámetros que admite

* `question`: pregunta de negocio en lenguaje natural.
* `database_url`: conexión SQLAlchemy.
* `schema_csv_path`: ruta al CSV del esquema.
* `sql_query`: SQL opcional, si quieres controlar manualmente la consulta.
* `max_rows`: máximo de filas a devolver.

### Consideraciones del workshop

* La validación bloquea operaciones destructivas como `INSERT`, `UPDATE`, `DELETE`, `DROP` o `ALTER`.
* Para motores distintos de SQLite, puede hacer falta instalar el driver correspondiente, por ejemplo `psycopg` para Postgres o `pyodbc` para SQL Server.
* El CSV no reemplaza el catálogo real de la base, pero es una forma muy didáctica de guiar al modelo para primeros ejercicios.

---

## 👩‍💻 Autoria

Desarrollado como demo técnica para charlas internas sobre **multiagentes y LangGraph**.
