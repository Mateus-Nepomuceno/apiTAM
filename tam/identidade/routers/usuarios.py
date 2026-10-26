from http import HTTPStatus
from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from tam.core.security import (
    exigir_perfil,
    get_current_user,
    get_optional_user,
    get_password_hash,
)
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import (
    PerfilUsuario,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)

router = APIRouter(prefix='/usuarios', tags=['usuarios'])


@router.post(
    '/', response_model=UsuarioResponse, status_code=HTTPStatus.CREATED
)
async def criar_usuario(
    usuario_in: UsuarioCreate,
    usuario_atual: Annotated[UsuarioModel | None, Depends(get_optional_user)],
):
    primeiro_usuario = await UsuarioModel.find_one() is None
    if not primeiro_usuario and (
        usuario_atual is None or usuario_atual.perfil != PerfilUsuario.ADMIN
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Apenas administradores podem criar usuários.',
        )

    usuario_existente = await UsuarioModel.find_one(
        UsuarioModel.email == usuario_in.email
    )
    if usuario_existente:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail='E-mail já registado na plataforma.',
        )

    dados_usuario = usuario_in.model_dump()
    dados_usuario['senha'] = get_password_hash(dados_usuario['senha'])
    if primeiro_usuario:
        dados_usuario['perfil'] = PerfilUsuario.ADMIN

    novo_usuario = UsuarioModel(**dados_usuario)
    await novo_usuario.insert()

    return novo_usuario


@router.get('/', response_model=list[UsuarioResponse])
async def listar_usuarios(
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
    limit: int = 100,
    skip: int = 0,
):
    usuarios = await UsuarioModel.find_all().skip(skip).limit(limit).to_list()
    return usuarios


@router.get('/{usuario_id}', response_model=UsuarioResponse)
async def obter_usuario(
    usuario_id: PydanticObjectId,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    usuario = await UsuarioModel.get(usuario_id)
    if not usuario:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Utilizador não encontrado.',
        )
    return usuario


@router.patch('/{usuario_id}', response_model=UsuarioResponse)
async def atualizar_usuario(
    usuario_id: PydanticObjectId,
    usuario_in: UsuarioUpdate,
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    usuario = await UsuarioModel.get(usuario_id)
    if not usuario:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Utilizador não encontrado.',
        )

    if (
        usuario_atual.perfil == PerfilUsuario.MEMBRO
        and usuario.id != usuario_atual.id
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Você só pode editar o seu próprio usuário.',
        )

    if (
        usuario_atual.perfil == PerfilUsuario.GESTOR
        and usuario.perfil == PerfilUsuario.ADMIN
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Gestores não podem editar administradores.',
        )

    dados_atualizacao = usuario_in.model_dump(
        exclude_unset=True, exclude_none=True
    )

    if (
        'perfil' in dados_atualizacao
        and dados_atualizacao['perfil'] != usuario.perfil
        and usuario_atual.perfil != PerfilUsuario.ADMIN
        and (
            usuario_atual.perfil != PerfilUsuario.GESTOR
            or dados_atualizacao['perfil'] == PerfilUsuario.ADMIN
        )
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Permissão insuficiente para alterar o perfil.',
        )

    if 'senha' in dados_atualizacao:
        dados_atualizacao['senha'] = get_password_hash(
            dados_atualizacao['senha']
        )

    if usuario_in.email and usuario_in.email != usuario.email:
        email_existente = await UsuarioModel.find_one(
            UsuarioModel.email == usuario_in.email
        )
        if email_existente:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail='E-mail já se encontra em uso.',
            )

    for campo, valor in dados_atualizacao.items():
        setattr(usuario, campo, valor)

    await usuario.save()
    return usuario


@router.delete('/{usuario_id}', status_code=HTTPStatus.NO_CONTENT)
async def apagar_usuario(
    usuario_id: PydanticObjectId,
    usuario_atual: Annotated[
        UsuarioModel, Depends(exigir_perfil(PerfilUsuario.ADMIN))
    ],
):
    usuario = await UsuarioModel.get(usuario_id)
    if not usuario:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail='Utilizador não encontrado.',
        )

    if usuario.id == usuario_atual.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail='Não pode apagar a sua própria conta.',
        )

    await usuario.delete()
