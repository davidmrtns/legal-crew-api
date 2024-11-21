import io
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse
from typing_extensions import Optional
from app.db.database import obter_sessao
from app.db.models import Conversa, Assistente, Arquivo, Usuario
from app.utils.assistant import Assistant
from app.utils.auth import obter_usuario_logado
from app.utils.tools import ToolMapper


router = APIRouter(
    dependencies=[Depends(obter_usuario_logado)]
)


@router.get("/{nome}")
async def obter_assistente(nome: str, db: Session = Depends(obter_sessao)):
    assistente = db.query(Assistente).filter_by(slug=nome).first()
    if assistente is not None:
        return assistente
    return {"erro": "O assistente não foi encontrado"}


'''Rota para listar os assistentes disponíveis'''
@router.get("/todos/listar")
async def listar_assistentes(db: Session = Depends(obter_sessao)):
    assistentes = db.query(Assistente).all()
    return assistentes


'''Rota para obter o nome do assistente'''
@router.get("/{assistant_id}/nome")
async def obter_nome_assistente(assistant_id: str, db: Session = Depends(obter_sessao)):
    assistente_bd = db.query(Assistente).filter_by(id=assistant_id).first()

    if assistente_bd is not None:
        return assistente_bd.nome
    return {"erro": "O assistente não foi encontrado"}


'''Rota para iniciar interação com um assistente específico pelo nome'''
@router.post("/{nome}/chat")
async def executar(
        nome: str,
        mensagem: str = Form(...),
        arquivos: Optional[UploadFile] = File(None),
        db: Session = Depends(obter_sessao),
        usuario: Usuario = Depends(obter_usuario_logado)
):
    if usuario is not None:
        assistente_bd = db.query(Assistente).filter_by(slug=nome).first()

        if assistente_bd is not None:
            nomes_ferramentas = [tool.nome for tool in assistente_bd.ferramentas]
            ferramentas = ToolMapper.mapear_ferramentas(nomes_ferramentas)

            assistente = Assistant(nome=assistente_bd.nome, id=assistente_bd.id, tools=ferramentas)
            assistente.adicionar_mensagens([mensagem], None)

            if arquivos is not None:
                assistente.adicionar_arquivos(arquivos)
                await assistente.processar_arquivos(None)

            resultado, thread_id = assistente.criar_rodar_thread()

            conversa = Conversa(id_assistente=assistente.id, id_thread=thread_id, id_usuario=usuario.id)
            db.add(conversa)
            db.commit()
            db.refresh(conversa)
            return {"thread_id": thread_id}
        return {"erro": "O assistente que você chamou não foi encontrado"}


'''Rota para adicionar mensagem a uma thread'''
@router.post("/thread/{thread_id}")
async def enviar_mensagem(
        thread_id: str,
        assistente: str = Form(...),
        mensagem: str = Form(...),
        arquivos: Optional[UploadFile] = File(None),
        db: Session = Depends(obter_sessao)
):
    if thread_id:
        assistente_bd = db.query(Assistente).filter_by(slug=assistente).first()

        if assistente_bd is not None:
            nomes_ferramentas = [tool.nome for tool in assistente_bd.ferramentas]
            ferramentas = ToolMapper.mapear_ferramentas(nomes_ferramentas)
            assistente = Assistant(nome=assistente_bd.nome, id=assistente_bd.id, tools=ferramentas)
            assistente.adicionar_mensagens([mensagem], thread_id)

            if arquivos is not None:
                assistente.adicionar_arquivos(arquivos)
                await assistente.processar_arquivos(thread_id)
            return assistente.rodar_thread(thread_id)

        return {"erro": "O assistente que você chamou não foi encontrado"}
    return {"erro": "ID da thread em branco"}


'''Rota para obter as mensagens de uma thread'''
@router.get("/thread/{thread_id}")
async def listar_mensagens(
        thread_id: str,
        db: Session = Depends(obter_sessao),
        usuario: Usuario = Depends(obter_usuario_logado)
):
    conversa = db.query(Conversa).filter_by(id_thread=thread_id, id_usuario=usuario.id).first()

    if conversa is not None:
        assistente = Assistant(nome=conversa.assistente.nome, id=conversa.assistente.id, tools=[])
        return {"assistente": conversa.assistente, "mensagens": assistente.listar_mensagens_thread(thread_id)}
    return {"erro": "Conversa não localizada"}


@router.get("/thread/{thread_id}/arquivo/{file_id}")
async def baixar_arquivo(
        thread_id: str,
        file_id: str,
        db: Session = Depends(obter_sessao),
        usuario: Usuario = Depends(obter_usuario_logado)
):
    conversa = db.query(Conversa).filter_by(id_thread=thread_id, id_usuario=usuario.id).first()

    if conversa is not None:
        arquivo = db.query(Arquivo).filter_by(id=file_id, id_conversa=conversa.id).first()

        if arquivo is not None:
            assistente = Assistant(nome=conversa.assistente.nome, id=conversa.assistente.id, tools=[])
            conteudo = assistente.obter_arquivo(file_id)
            return StreamingResponse(
                io.BytesIO(conteudo.content),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={file_id}.png"}
            )
    return {"erro": "Não foi possível encontrar o arquivo"}
