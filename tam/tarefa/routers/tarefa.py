from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from tam.core.security import get_current_user
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import PerfilUsuario
from tam.projeto.models import ProjetoModel
from tam.projeto.routers.projeto import participa_do_projeto
from tam.tarefa.models import (
    COLUNA_POR_STATUS,
    STATUS_POR_COLUNA,
    ColunaQuadro,
    Comentario,
    HistoricoStatusTarefa,
    ItemChecklist,
    StatusTarefa,
    TarefaModel,
)
from tam.tarefa.schemas import (
    ComentarioCreate,
    FiltroTarefa,
    TarefaCreate,
    TarefaResponse,
    TarefaUpdate,
)

router = APIRouter(prefix='/tarefas', tags=['tarefas'])


async def _membro_participa(
    projeto_id: PydanticObjectId | None, usuario: UsuarioModel
) -> bool:
    if projeto_id is None:
        return False
    projeto = await ProjetoModel.get(projeto_id)
    return bool(projeto and participa_do_projeto(projeto, usuario))


async def _pode_alterar(tarefa: TarefaModel, usuario: UsuarioModel) -> bool:
    if usuario.perfil != PerfilUsuario.MEMBRO:
        return True
    if usuario.id in {tarefa.responsavel_id, tarefa.criador_id}:
        return True
    return await _membro_participa(tarefa.projeto_id, usuario)


async def _garantir_projeto_acessivel(
    projeto_id: PydanticObjectId | None, usuario: UsuarioModel
):
    if projeto_id is None:
        return
    projeto = await ProjetoModel.get(projeto_id)
    if not projeto:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Projeto não encontrado.',
        )
    if usuario.perfil == PerfilUsuario.MEMBRO and not participa_do_projeto(
        projeto, usuario
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você só pode criar tarefas em projetos '
            'dos quais participa.',
        )


def _sincronizar_coluna_e_status(dados: dict, coluna_atual: ColunaQuadro):
    if 'coluna_quadro' in dados:
        dados['status'] = STATUS_POR_COLUNA[dados['coluna_quadro']]
    elif 'status' in dados:
        if STATUS_POR_COLUNA.get(coluna_atual) != dados['status']:
            dados['coluna_quadro'] = COLUNA_POR_STATUS[dados['status']]


def _normalizar_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.post(
    '/', response_model=TarefaResponse, status_code=HTTPStatus.CREATED
)
async def criar_tarefa(
    tarefa_in: TarefaCreate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    await _garantir_projeto_acessivel(tarefa_in.projeto_id, usuario_atual)

    dados = tarefa_in.model_dump()
    if not dados.get('criador_id'):
        dados['criador_id'] = usuario_atual.id

    if dados.get('coluna_quadro') is not None:
        dados['status'] = STATUS_POR_COLUNA[dados['coluna_quadro']]
    elif dados.get('status') is not None:
        dados['coluna_quadro'] = COLUNA_POR_STATUS[dados['status']]
    else:
        dados['status'] = StatusTarefa.PENDENTE
        dados['coluna_quadro'] = ColunaQuadro.BACKLOG
    if dados['status'] == StatusTarefa.CONCLUIDA:
        dados['data_conclusao'] = datetime.now(timezone.utc)

    if dados.get('checklist'):
        dados['checklist'] = [
            ItemChecklist(**item) if isinstance(item, dict) else item
            for item in dados['checklist']
        ]

    nova_tarefa = TarefaModel(**dados)
    await nova_tarefa.insert()
    return nova_tarefa


@router.get('/', response_model=list[TarefaResponse])
async def listar_tarefas(
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
    filtros: Annotated[FiltroTarefa, Depends()],
):
    criterios = []
    if filtros.projeto_id is not None:
        criterios.append(TarefaModel.projeto_id == filtros.projeto_id)
    if filtros.responsavel_id is not None:
        criterios.append(TarefaModel.responsavel_id == filtros.responsavel_id)
    if filtros.status is not None:
        criterios.append(TarefaModel.status == filtros.status)
    if filtros.prioridade is not None:
        criterios.append(TarefaModel.prioridade == filtros.prioridade)
    if filtros.etiqueta is not None:
        criterios.append(TarefaModel.etiquetas == filtros.etiqueta)

    if criterios:
        tarefas = (
            await TarefaModel
            .find(*criterios)
            .skip(filtros.skip)
            .limit(filtros.limit)
            .to_list()
        )
    else:
        tarefas = (
            await TarefaModel
            .find_all()
            .skip(filtros.skip)
            .limit(filtros.limit)
            .to_list()
        )

    return tarefas


@router.get('/{tarefa_id}', response_model=TarefaResponse)
async def obter_tarefa(
    tarefa_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    tarefa = await TarefaModel.get(tarefa_id)
    if not tarefa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tarefa não encontrada.',
        )
    return tarefa


@router.patch('/{tarefa_id}', response_model=TarefaResponse)
async def atualizar_tarefa(
    tarefa_id: PydanticObjectId,
    tarefa_in: TarefaUpdate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    tarefa = await TarefaModel.get(tarefa_id)
    if not tarefa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tarefa não encontrada.',
        )

    if not await _pode_alterar(tarefa, usuario_atual):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Permissão insuficiente para alterar esta tarefa.',
        )

    if (
        tarefa_in.projeto_id is not None
        and tarefa_in.projeto_id != tarefa.projeto_id
    ):
        await _garantir_projeto_acessivel(tarefa_in.projeto_id, usuario_atual)

    dados_atualizacao = tarefa_in.model_dump(
        exclude_unset=True, exclude_none=True
    )

    if 'data_prazo' in tarefa_in.model_fields_set and (
        tarefa_in.data_prazo is None
    ):
        tarefa.data_prazo = None

    _sincronizar_coluna_e_status(dados_atualizacao, tarefa.coluna_quadro)

    nova_inicio = dados_atualizacao.get('data_inicio', tarefa.data_inicio)
    novo_prazo = dados_atualizacao.get('data_prazo', tarefa.data_prazo)
    inicio_utc = _normalizar_utc(nova_inicio)
    prazo_utc = _normalizar_utc(novo_prazo)
    if prazo_utc and inicio_utc and prazo_utc < inicio_utc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail='A data de prazo não pode ser anterior à data de início.',
        )

    novo_comentario = dados_atualizacao.pop('novo_comentario', None)
    if novo_comentario:
        tarefa.comentarios.append(
            Comentario(
                autor_id=usuario_atual.id,
                texto=novo_comentario,
            )
        )

    if (
        'status' in dados_atualizacao
        and dados_atualizacao['status'] != tarefa.status
    ):
        historico = HistoricoStatusTarefa(
            status_anterior=tarefa.status,
            status_novo=dados_atualizacao['status'],
            data_alteracao=datetime.now(timezone.utc),
            autor_id=usuario_atual.id,
        )
        tarefa.historico_status.append(historico)

        if dados_atualizacao['status'] == StatusTarefa.CONCLUIDA:
            tarefa.data_conclusao = datetime.now(timezone.utc)
        elif tarefa.status == StatusTarefa.CONCLUIDA:
            tarefa.data_conclusao = None

    if 'checklist' in dados_atualizacao:
        tarefa.checklist = [
            ItemChecklist(**item) if isinstance(item, dict) else item
            for item in dados_atualizacao.pop('checklist')
        ]

    for campo, valor in dados_atualizacao.items():
        setattr(tarefa, campo, valor)

    tarefa.atualizado_em = datetime.now(timezone.utc)
    await tarefa.save()
    return tarefa


@router.delete('/{tarefa_id}', status_code=HTTPStatus.NO_CONTENT)
async def apagar_tarefa(
    tarefa_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    tarefa = await TarefaModel.get(tarefa_id)
    if not tarefa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tarefa não encontrada.',
        )

    if (
        usuario_atual.perfil == PerfilUsuario.MEMBRO
        and tarefa.criador_id != usuario_atual.id
        and not await _membro_participa(tarefa.projeto_id, usuario_atual)
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Permissão insuficiente para excluir esta tarefa.',
        )

    await tarefa.delete()


@router.post(
    '/{tarefa_id}/comentarios',
    response_model=TarefaResponse,
    status_code=HTTPStatus.CREATED,
)
async def adicionar_comentario(
    tarefa_id: PydanticObjectId,
    comentario_in: ComentarioCreate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    tarefa = await TarefaModel.get(tarefa_id)
    if not tarefa:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Tarefa não encontrada.',
        )

    tarefa.comentarios.append(
        Comentario(
            autor_id=usuario_atual.id,
            texto=comentario_in.texto,
        )
    )
    tarefa.atualizado_em = datetime.now(timezone.utc)
    await tarefa.save()
    return tarefa
