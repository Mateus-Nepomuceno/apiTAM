from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated, Optional

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from tam.core.security import exigir_perfil, get_current_user
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import PerfilUsuario
from tam.projeto.models import (
    HistoricoStatus,
    ProjetoModel,
    SaudeProjeto,
    StatusProjeto,
)
from tam.projeto.schemas import ProjetoCreate, ProjetoResponse, ProjetoUpdate
from tam.tarefa.models import TarefaModel

router = APIRouter(prefix='/projetos', tags=['projetos'])


def participa_do_projeto(projeto: ProjetoModel, usuario: UsuarioModel):
    return (
        projeto.responsavel_id == usuario.id
        or usuario.id in projeto.membros_equipe
    )


def _garantir_gestao(projeto: ProjetoModel, usuario: UsuarioModel):
    if usuario.perfil == PerfilUsuario.ADMIN:
        return
    if not participa_do_projeto(projeto, usuario):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você só pode gerenciar projetos dos quais participa.',
        )


async def _buscar_projeto(projeto_id: PydanticObjectId) -> ProjetoModel:
    projeto = await ProjetoModel.get(projeto_id)
    if not projeto:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Projeto não encontrado.',
        )
    return projeto


def _normalizar_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.post(
    '/', response_model=ProjetoResponse, status_code=HTTPStatus.CREATED
)
async def criar_projeto(
    projeto_in: ProjetoCreate,
    usuario_atual: Annotated[
        UsuarioModel,
        Depends(exigir_perfil(PerfilUsuario.GESTOR, PerfilUsuario.ADMIN)),
    ],
):
    novo_projeto = ProjetoModel(**projeto_in.model_dump())
    novo_projeto.historico_status = [
        HistoricoStatus(
            status_novo=novo_projeto.status,
            autor_id=usuario_atual.id,
            nota='Projeto criado',
        )
    ]
    await novo_projeto.insert()
    return novo_projeto


@router.get('/', response_model=list[ProjetoResponse])
async def listar_projetos(
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
    status: Optional[StatusProjeto] = None,
    saude: Optional[SaudeProjeto] = None,
    skip: int = 0,
    limit: int = 100,
):
    criterios = []
    if status is not None:
        criterios.append(ProjetoModel.status == status)
    if saude is not None:
        criterios.append(ProjetoModel.saude_projeto == saude)

    if criterios:
        projetos = (
            await ProjetoModel
            .find(*criterios)
            .skip(skip)
            .limit(limit)
            .to_list()
        )
    else:
        projetos = (
            await ProjetoModel.find_all().skip(skip).limit(limit).to_list()
        )
    return projetos


@router.get('/{projeto_id}', response_model=ProjetoResponse)
async def obter_projeto(
    projeto_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    projeto = await ProjetoModel.get(projeto_id)
    if not projeto:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Projeto não encontrado.',
        )
    return projeto


@router.patch('/{projeto_id}', response_model=ProjetoResponse)
async def atualizar_projeto(
    projeto_id: PydanticObjectId,
    projeto_in: ProjetoUpdate,
    usuario_atual: Annotated[
        UsuarioModel,
        Depends(exigir_perfil(PerfilUsuario.GESTOR, PerfilUsuario.ADMIN)),
    ],
):
    projeto = await _buscar_projeto(projeto_id)
    _garantir_gestao(projeto, usuario_atual)

    dados_atualizacao = projeto_in.model_dump(
        exclude_unset=True, exclude_none=True
    )

    nova_inicio = dados_atualizacao.get('data_inicio', projeto.data_inicio)
    nova_entrega = dados_atualizacao.get('data_entrega', projeto.data_entrega)
    inicio_utc = _normalizar_utc(nova_inicio)
    entrega_utc = _normalizar_utc(nova_entrega)
    if entrega_utc and inicio_utc and entrega_utc < inicio_utc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='A data de entrega não pode ser anterior à data de início.',
        )

    if (
        'status' in dados_atualizacao
        and dados_atualizacao['status'] != projeto.status
    ):
        historico = HistoricoStatus(
            status_anterior=projeto.status,
            status_novo=dados_atualizacao['status'],
            data_alteracao=datetime.now(timezone.utc),
            autor_id=usuario_atual.id,
            nota='Status atualizado',
        )
        projeto.historico_status.append(historico)

    for campo, valor in dados_atualizacao.items():
        setattr(projeto, campo, valor)

    await projeto.save()
    return projeto


@router.post(
    '/{projeto_id}/marcos/{indice}/alternar', response_model=ProjetoResponse
)
async def alternar_marco(
    projeto_id: PydanticObjectId,
    indice: int,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    projeto = await _buscar_projeto(projeto_id)

    if usuario_atual.perfil != PerfilUsuario.ADMIN and not (
        participa_do_projeto(projeto, usuario_atual)
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você não participa deste projeto.',
        )

    if not 0 <= indice < len(projeto.marcos):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Marco não encontrado.',
        )

    marco = projeto.marcos[indice]
    marco.concluido = not marco.concluido
    await projeto.save()
    return projeto


@router.delete('/{projeto_id}', status_code=HTTPStatus.NO_CONTENT)
async def apagar_projeto(
    projeto_id: PydanticObjectId,
    usuario_atual: Annotated[
        UsuarioModel,
        Depends(exigir_perfil(PerfilUsuario.GESTOR, PerfilUsuario.ADMIN)),
    ],
):
    projeto = await _buscar_projeto(projeto_id)
    _garantir_gestao(projeto, usuario_atual)

    await TarefaModel.find(TarefaModel.projeto_id == projeto.id).delete()
    await projeto.delete()
