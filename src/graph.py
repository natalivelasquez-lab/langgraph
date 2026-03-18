# src/graph.py
"""
LangGraph - Plantilla Multiagente (patrón 'agent tool-use')..

Qué hace este archivo:
1) Define un State con merge correcto (messages se acumula).
2) Crea un grafo LangGraph con:
   - Nodo 'agent': llama al LLM (Azure OpenAI) con tools bindeadas
   - Nodo 'tools': ejecuta tools (ToolNode)
   - Loop agent <-> tools hasta que no haya más tool_calls
3) Compila el grafo y guarda un diagrama Mermaid en /artifacts/graph.mmd
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict, List, Annotated

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_openai import AzureChatOpenAI

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages  # ✅ merge correcto del historial

from src.tools.weather import get_weather
from src.tools.image import generate_image
from src.tools.sql import query_sql_database
import logging
logger = logging.getLogger("langgraph-demo.graph")

# -----------------------------
# 1) Estado compartido del grafo
# -----------------------------
class AgentState(TypedDict):
    """
    messages: historial del chat.
    add_messages garantiza que cada nodo "agrega" mensajes en vez de reemplazarlos.
    """
    messages: Annotated[List[BaseMessage], add_messages]


# -----------------------------
# 2) Prompt de sistema (editable)
# -----------------------------
def _load_system_prompt() -> str:
    """
    Carga el prompt desde /src/prompts/system.md.
    Si no existe, usa un prompt por defecto (para que el repo siempre arranque).
    """
    p = Path(__file__).parent / "prompts" / "system.md"
    if p.exists():
        return p.read_text(encoding="utf-8")

    return (
        "Eres un asistente técnico. Responde en español, claro y breve.\n\n"
        "Si la pregunta requiere datos externos, usa una herramienta.\n"
        "Herramientas disponibles:\n"
        "- get_weather(location): clima actual por ciudad\n"
        "- generate_image(prompt): genera imagen y retorna ruta\n\n"
        "Si el usuario pregunta por clima, extrae la ciudad del mensaje y llama get_weather.\n"
        "Si el usuario pide una imagen, llama generate_image con un prompt corto.\n"
        "Después de usar herramientas, redacta la respuesta final."
    )


# -----------------------------
# 3) LLM Azure OpenAI - Agente principal
# -----------------------------
def _get_llm() -> AzureChatOpenAI:
    """
    LLM único. Usamos AzureChatOpenAI.
    Requiere:
    - AZURE_OPENAI_ENDPOINT
    - AZURE_OPENAI_API_KEY
    - AZURE_OPENAI_API_VERSION
    - AZURE_OPENAI_CHAT_DEPLOYMENT
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")

    if not endpoint:
        raise RuntimeError("Falta AZURE_OPENAI_ENDPOINT. ¿Cargaste el .env?")
    if not api_key:
        raise RuntimeError("Falta AZURE_OPENAI_API_KEY. ¿Cargaste el .env?")
    if not deployment:
        raise RuntimeError("Falta AZURE_OPENAI_CHAT_DEPLOYMENT. ¿Cargaste el .env?")

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=deployment,
        temperature=0.2,
    )


# -----------------------------
# 4) Construcción del grafo
# -----------------------------
def build_graph(save_diagram: bool = True):
    """
    Construye y compila el grafo. Con save_diagram=True guarda Mermaid.
    """

    # Tools registradas con @tool
    tools = [get_weather, generate_image, query_sql_database]
    tool_node = ToolNode(tools)

    # LLM + tools (habilita tool calling)
    llm = _get_llm().bind_tools(tools)

    system_msg = SystemMessage(content=_load_system_prompt())

    def agent_node(state: AgentState) -> dict:
        logger.info("🧠 [AGENT] Ejecutando agente principal")

        msgs = state["messages"]

        if not msgs or not isinstance(msgs[0], SystemMessage):
            logger.debug("🧠 [AGENT] Inyectando SystemPrompt")
            msgs = [system_msg] + msgs

        logger.debug(f"🧠 [AGENT] Mensajes actuales: {len(msgs)}")

        ai_msg = llm.invoke(msgs)

        if getattr(ai_msg, "tool_calls", None):
            logger.info("🔧 [AGENT] El modelo decidió usar una tool")
            for tc in ai_msg.tool_calls:
                logger.info(f"🔧 [AGENT] Tool solicitada: {tc['name']} | args={tc['args']}")
        else:
            logger.info("🧠 [AGENT] El modelo NO solicitó tools (respuesta directa)")

        return {"messages": [ai_msg]}


    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]

        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            logger.info("➡️ [GRAPH] Transición a nodo TOOLS")
            return "tools"

        logger.info("⏹️ [GRAPH] Finalizando ejecución del grafo")
        return "end"


    g = StateGraph(AgentState)

    g.add_node("agent", agent_node)
    g.add_node("tools", tool_node)

    g.set_entry_point("agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    g.add_edge("tools", "agent")

    app = g.compile()

    if save_diagram:
        _save_mermaid_diagram(app)

    return app


def _save_mermaid_diagram(compiled_graph):
    """
    Exporta un diagrama Mermaid del grafo en /artifacts/graph.mmd
    """
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "graph.mmd"
    try:
        mermaid = compiled_graph.get_graph().draw_mermaid()
        out_path.write_text(mermaid, encoding="utf-8")
    except Exception as e:
        out_path.write_text(
            f"%% No pude generar Mermaid automáticamente.\n%% Error: {type(e).__name__}: {e}\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    _ = build_graph(save_diagram=True)
    print("OK: grafo compilado y diagrama guardado en artifacts/graph.mmd")
