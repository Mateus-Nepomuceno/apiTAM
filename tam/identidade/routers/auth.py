from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from tam.core.security import (
    create_access_token,
    get_current_user,
    verify_password,
)
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import Token, UsuarioResponse

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/token', response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    usuario = await UsuarioModel.find_one(
        UsuarioModel.email == form_data.username
    )

    if not usuario:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Senha ou email incorretos',
        )

    if not verify_password(form_data.password, usuario.senha):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail='Senha ou email incorretos',
        )

    access_token = create_access_token(
        data={
            'sub': usuario.email,
            'id': str(usuario.id),
            'perfil': usuario.perfil.value,
        }
    )

    return {'access_token': access_token, 'token_type': 'bearer'}


@router.get('/me', response_model=UsuarioResponse)
async def usuario_logado(
    usuario_atual: Annotated[UsuarioModel, Depends(get_current_user)],
):
    return usuario_atual
