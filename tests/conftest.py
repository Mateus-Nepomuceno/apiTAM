from datetime import datetime, timedelta, timezone
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
from tam.projeto.models import ProjetoModel, SaudeProjeto, StatusProjeto
from tam.tarefa.models import PrioridadeTarefa, StatusTarefa, TarefaModel

TEST_DB_NAME = 'tam_test'
SENHA_PADRAO = 'senha-segura-123'


@pytest.fixture(scope='session')
def client():
    mongo = AsyncMongoClient(Settings().DATABASE_URL)

    async def init_test_db():
        await init_beanie(
            database=mongo[TEST_DB_NAME],
            document_models=[UsuarioModel, ProjetoModel, TarefaModel],
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
    client.portal.call(ProjetoModel.delete_all)
    client.portal.call(TarefaModel.delete_all)


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


@pytest.fixture
def criar_projeto(client, admin):
    contador = count()

    def _criar(responsavel=None, **campos):
        n = next(contador)
        resp = responsavel or admin
        agora = datetime.now(timezone.utc)
        projeto = ProjetoModel(
            nome=campos.get('nome', f'Projeto {n}'),
            descricao=campos.get('descricao', f'Descrição {n}'),
            responsavel_id=resp.id,
            status=campos.get('status', StatusProjeto.PLANEJAMENTO),
            saude_projeto=campos.get('saude_projeto', SaudeProjeto.NO_PRAZO),
            percentual_progresso=campos.get('percentual_progresso', 0.0),
            membros_equipe=campos.get('membros_equipe', []),
            marcos=campos.get('marcos', []),
            historico_status=campos.get('historico_status', []),
            data_inicio=campos.get('data_inicio', agora),
            data_entrega=campos.get(
                'data_entrega', agora + timedelta(days=30)
            ),
        )
        client.portal.call(projeto.insert)
        return projeto

    return _criar


@pytest.fixture
def criar_tarefa(client, admin):
    contador = count()

    def _criar(criador=None, responsavel=None, **campos):
        n = next(contador)
        criador_usuario = criador or admin
        agora = datetime.now(timezone.utc)
        tarefa = TarefaModel(
            titulo=campos.get('titulo', f'Tarefa {n}'),
            descricao=campos.get('descricao', f'Descrição da tarefa {n}'),
            projeto_id=campos.get('projeto_id', None),
            responsavel_id=responsavel.id if responsavel else None,
            criador_id=criador_usuario.id,
            status=campos.get('status', StatusTarefa.PENDENTE),
            prioridade=campos.get('prioridade', PrioridadeTarefa.MEDIA),
            etiquetas=campos.get('etiquetas', []),
            checklist=campos.get('checklist', []),
            comentarios=campos.get('comentarios', []),
            historico_status=campos.get('historico_status', []),
            data_inicio=campos.get('data_inicio', agora),
            data_prazo=campos.get('data_prazo', agora + timedelta(days=7)),
        )
        client.portal.call(tarefa.insert)
        return tarefa

    return _criar
