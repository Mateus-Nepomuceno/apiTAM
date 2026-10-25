from http import HTTPStatus
from itertools import count

import pytest
from beanie import init_beanie
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient

from tam import app as app_module
from tam.core.security import get_password_hash
from tam.core.settings import Settings
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import PerfilUsuario
from tam.treinamento.models import (
    MatriculaTreinamentoModel,
    TreinamentoModel,
)

TEST_DB_NAME = 'tam_test'
SENHA_PADRAO = 'senha-segura-123'


@pytest.fixture(scope='session')
def client():
    mongo = AsyncMongoClient(Settings().DATABASE_URL)

    async def init_test_db():
        await init_beanie(
            database=mongo[TEST_DB_NAME],
            document_models=[
                UsuarioModel,
                TreinamentoModel,
                MatriculaTreinamentoModel,
            ],
        )

    mp = pytest.MonkeyPatch()
    mp.setattr(app_module, 'init_db', init_test_db)

    with TestClient(app_module.app) as test_client:
        yield test_client
        test_client.portal.call(mongo.drop_database, TEST_DB_NAME)
        test_client.portal.call(mongo.close)

    mp.undo()


@pytest.fixture(autouse=True)
def limpar_banco(client):
    client.portal.call(UsuarioModel.delete_all)
    client.portal.call(TreinamentoModel.delete_all)
    client.portal.call(MatriculaTreinamentoModel.delete_all)


@pytest.fixture
def criar_usuario(client):
    contador = count()

    def _criar(perfil: PerfilUsuario = PerfilUsuario.MEMBRO, **campos):
        n = next(contador)
        usuario = UsuarioModel(
            nome=campos.get('nome', f'Usuário {n}'),
            email=campos.get('email', f'{perfil.value.lower()}{n}@test.com'),
            perfil=perfil,
            departamento=campos.get('departamento', 'TI'),
            senha=get_password_hash(SENHA_PADRAO),
        )
        client.portal.call(usuario.insert)
        return usuario

    return _criar


@pytest.fixture
def token_de(client):
    def _token(usuario: UsuarioModel):
        response = client.post(
            '/auth/token',
            data={'username': usuario.email, 'password': SENHA_PADRAO},
        )
        assert response.status_code == HTTPStatus.OK, response.text
        return {'Authorization': f'Bearer {response.json()["access_token"]}'}

    return _token


@pytest.fixture
def admin(criar_usuario):
    return criar_usuario(PerfilUsuario.ADMIN)


@pytest.fixture
def gestor(criar_usuario):
    return criar_usuario(PerfilUsuario.GESTOR)


@pytest.fixture
def membro(criar_usuario):
    return criar_usuario(PerfilUsuario.MEMBRO)
