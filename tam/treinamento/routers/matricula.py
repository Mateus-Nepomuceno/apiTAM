from datetime import datetime, timezone
from http import HTTPStatus
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from tam.core.security import exigir_perfil, get_current_user
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import PerfilUsuario
from tam.treinamento.models import (
    MatriculaTreinamentoModel,
    TreinamentoModel,
)
from tam.treinamento.schemas import (
    MatriculaCreate,
    MatriculaResponse,
    MatriculaUpdate,
    StatusMatricula,
)

router = APIRouter(prefix='/matriculas', tags=['matriculas'])

CAMPOS_RESTRITOS_MEMBRO = {'percentual_progresso', 'url_certificado'}
PROGRESSO_COMPLETO = 100


class FiltroMatricula(BaseModel):
    aluno_id: PydanticObjectId | None = None
    treinamento_id: PydanticObjectId | None = None
    status: StatusMatricula | None = None
    limit: int = 100
    skip: int = 0


async def _buscar_matricula(matricula_id: PydanticObjectId):
    matricula = await MatriculaTreinamentoModel.get(matricula_id)
    if not matricula:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Matrícula não encontrada.',
        )
    return matricula


def _garantir_acesso(matricula: MatriculaTreinamentoModel, usuario):
    if (
        usuario.perfil == PerfilUsuario.MEMBRO
        and matricula.aluno_id != usuario.id
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você só pode acessar as suas próprias matrículas.',
        )


@router.post(
    '/', response_model=MatriculaResponse, status_code=HTTPStatus.CREATED
)
async def criar_matricula(
    matricula_in: MatriculaCreate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    aluno_id = matricula_in.aluno_id or usuario_atual.id

    if (
        usuario_atual.perfil == PerfilUsuario.MEMBRO
        and aluno_id != usuario_atual.id
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você só pode matricular a si mesmo.',
        )

    if not await UsuarioModel.get(aluno_id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Aluno não encontrado.',
        )

    if not await TreinamentoModel.get(matricula_in.treinamento_id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Treinamento não encontrado.',
        )

    matricula_existente = await MatriculaTreinamentoModel.find_one(
        MatriculaTreinamentoModel.aluno_id == aluno_id,
        MatriculaTreinamentoModel.treinamento_id
        == matricula_in.treinamento_id,
        MatriculaTreinamentoModel.status != StatusMatricula.DESISTENTE,
    )
    if matricula_existente:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='Aluno já matriculado neste treinamento.',
        )

    nova_matricula = MatriculaTreinamentoModel(
        aluno_id=aluno_id, treinamento_id=matricula_in.treinamento_id
    )
    await nova_matricula.insert()

    return nova_matricula


@router.get('/', response_model=list[MatriculaResponse])
async def listar_matriculas(
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
    filtro: Annotated[FiltroMatricula, Query()],
):
    aluno_id = filtro.aluno_id
    if usuario_atual.perfil == PerfilUsuario.MEMBRO:
        aluno_id = usuario_atual.id

    filtros = []
    if aluno_id:
        filtros.append(MatriculaTreinamentoModel.aluno_id == aluno_id)
    if filtro.treinamento_id:
        filtros.append(
            MatriculaTreinamentoModel.treinamento_id == filtro.treinamento_id
        )
    if filtro.status:
        filtros.append(MatriculaTreinamentoModel.status == filtro.status)

    return (
        await MatriculaTreinamentoModel
        .find(*filtros)
        .skip(filtro.skip)
        .limit(filtro.limit)
        .to_list()
    )


@router.get('/{matricula_id}', response_model=MatriculaResponse)
async def obter_matricula(
    matricula_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    matricula = await _buscar_matricula(matricula_id)
    _garantir_acesso(matricula, usuario_atual)
    return matricula


@router.patch('/{matricula_id}', response_model=MatriculaResponse)
async def atualizar_matricula(
    matricula_id: PydanticObjectId,
    matricula_in: MatriculaUpdate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    matricula = await _buscar_matricula(matricula_id)
    _garantir_acesso(matricula, usuario_atual)

    dados = matricula_in.model_dump(exclude_unset=True, exclude_none=True)

    if usuario_atual.perfil == PerfilUsuario.MEMBRO:
        status_proibido = (
            'status' in dados and dados['status'] != StatusMatricula.DESISTENTE
        )
        if CAMPOS_RESTRITOS_MEMBRO & dados.keys() or status_proibido:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail='Você só pode concluir módulos ou desistir.',
            )

    if 'modulos_concluidos' in dados:
        treinamento = await TreinamentoModel.get(matricula.treinamento_id)
        ids_validos = (
            {modulo.id for modulo in treinamento.modulos}
            if treinamento
            else set()
        )
        concluidos = list(dict.fromkeys(dados['modulos_concluidos']))

        if any(modulo not in ids_validos for modulo in concluidos):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='Módulo inválido para este treinamento.',
            )

        dados['modulos_concluidos'] = concluidos
        if 'percentual_progresso' not in dados and ids_validos:
            dados['percentual_progresso'] = round(
                len(concluidos) / len(ids_validos) * 100, 2
            )

    for campo, valor in dados.items():
        setattr(matricula, campo, valor)

    em_curso = (StatusMatricula.MATRICULADO, StatusMatricula.EM_ANDAMENTO)
    if 'status' not in dados and matricula.status in em_curso:
        if matricula.percentual_progresso >= PROGRESSO_COMPLETO:
            matricula.status = StatusMatricula.CONCLUIDO
        elif matricula.percentual_progresso > 0:
            matricula.status = StatusMatricula.EM_ANDAMENTO

    if (
        matricula.status == StatusMatricula.CONCLUIDO
        and matricula.concluido_em is None
    ):
        matricula.concluido_em = datetime.now(timezone.utc)

    await matricula.save()
    return matricula


@router.delete('/{matricula_id}', status_code=HTTPStatus.NO_CONTENT)
async def apagar_matricula(
    matricula_id: PydanticObjectId,
    usuario_atual: Annotated[
        UsuarioModel,
        Depends(exigir_perfil(PerfilUsuario.ADMIN, PerfilUsuario.GESTOR)),
    ],
):
    matricula = await _buscar_matricula(matricula_id)
    await matricula.delete()
