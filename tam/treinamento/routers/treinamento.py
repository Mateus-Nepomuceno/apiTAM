import re
from http import HTTPStatus
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from tam.core.security import exigir_perfil, get_current_user
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import PerfilUsuario
from tam.treinamento.models import (
    MatriculaTreinamentoModel,
    TreinamentoModel,
)
from tam.treinamento.schemas import (
    CategoriaTreinamento,
    TreinamentoCreate,
    TreinamentoResponse,
    TreinamentoUpdate,
)

router = APIRouter(prefix='/treinamentos', tags=['treinamentos'])

GestaoTreinamento = Annotated[
    UsuarioModel,
    Depends(exigir_perfil(PerfilUsuario.ADMIN, PerfilUsuario.GESTOR)),
]


def _garantir_dono(treinamento: TreinamentoModel, usuario: UsuarioModel):
    if (
        usuario.perfil != PerfilUsuario.ADMIN
        and treinamento.instrutor_id != usuario.id
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Apenas o instrutor ou um administrador pode alterar '
            'este treinamento.',
        )


async def _garantir_instrutor(instrutor_id: PydanticObjectId):
    if not await UsuarioModel.get(instrutor_id):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Instrutor não encontrado.',
        )


@router.post(
    '/',
    response_model=TreinamentoResponse,
    status_code=HTTPStatus.CREATED,
)
async def criar_treinamento(
    treinamento_in: TreinamentoCreate,
    usuario_atual: GestaoTreinamento,
):
    dados = treinamento_in.model_dump()

    if dados['instrutor_id'] is None:
        dados['instrutor_id'] = usuario_atual.id
    else:
        await _garantir_instrutor(dados['instrutor_id'])

    novo_treinamento = TreinamentoModel(**dados)
    await novo_treinamento.insert()

    return novo_treinamento


@router.get('/', response_model=list[TreinamentoResponse])
async def listar_treinamentos(
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
    busca: str | None = None,
    categoria: CategoriaTreinamento | None = None,
    limit: int = 100,
    skip: int = 0,
):
    filtros = []
    if busca:
        filtros.append({
            'titulo': {'$regex': re.escape(busca), '$options': 'i'}
        })
    if categoria:
        filtros.append(TreinamentoModel.categoria == categoria)

    return (
        await TreinamentoModel.find(*filtros).skip(skip).limit(limit).to_list()
    )


@router.get('/{treinamento_id}', response_model=TreinamentoResponse)
async def obter_treinamento(
    treinamento_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    treinamento = await TreinamentoModel.get(treinamento_id)
    if not treinamento:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Treinamento não encontrado.',
        )
    return treinamento


@router.patch('/{treinamento_id}', response_model=TreinamentoResponse)
async def atualizar_treinamento(
    treinamento_id: PydanticObjectId,
    treinamento_in: TreinamentoUpdate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    treinamento = await TreinamentoModel.get(treinamento_id)
    if not treinamento:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Treinamento não encontrado.',
        )
    _garantir_dono(treinamento, usuario_atual)

    dados_atualizacao = treinamento_in.model_dump(
        exclude_unset=True, exclude_none=True
    )

    if 'instrutor_id' in dados_atualizacao:
        await _garantir_instrutor(dados_atualizacao['instrutor_id'])

    for campo, valor in dados_atualizacao.items():
        setattr(treinamento, campo, valor)

    await treinamento.save()
    return treinamento


@router.delete('/{treinamento_id}', status_code=HTTPStatus.NO_CONTENT)
async def apagar_treinamento(
    treinamento_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    treinamento = await TreinamentoModel.get(treinamento_id)
    if not treinamento:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Treinamento não encontrado.',
        )
    _garantir_dono(treinamento, usuario_atual)

    await MatriculaTreinamentoModel.find(
        MatriculaTreinamentoModel.treinamento_id == treinamento.id
    ).delete()
    await treinamento.delete()
