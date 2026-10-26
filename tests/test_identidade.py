from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest
from jwt import encode

from tam.core.security import settings, verify_password
from tam.identidade.models import UsuarioModel
from tam.identidade.schemas import PerfilUsuario

NOVO_USUARIO = {
    'nome': 'Fulano',
    'email': 'fulano@test.com',
    'perfil': 'Membro',
    'departamento': 'RH',
    'senha': 'outra-senha',
}


def buscar(client, usuario_id):
    return client.portal.call(UsuarioModel.get, usuario_id)


def test_login_retorna_token(client, membro):
    response = client.post(
        '/auth/token',
        data={'username': membro.email, 'password': 'senha-segura-123'},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['token_type'] == 'bearer'
    assert response.json()['access_token']


def test_login_com_senha_errada(client, membro):
    response = client.post(
        '/auth/token', data={'username': membro.email, 'password': 'errada'}
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_login_com_email_inexistente(client):
    response = client.post(
        '/auth/token',
        data={'username': 'naoexiste@test.com', 'password': 'qualquer'},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_rota_protegida_sem_token(client):
    response = client.get('/usuarios/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_token_invalido(client):
    response = client.get(
        '/usuarios/', headers={'Authorization': 'Bearer invalido'}
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_token_expirado(client, membro):
    token = encode(
        {
            'sub': membro.email,
            'exp': datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.get(
        '/usuarios/', headers={'Authorization': f'Bearer {token}'}
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_token_de_usuario_apagado(client, membro, token_de):
    headers = token_de(membro)
    client.portal.call(membro.delete)

    response = client.get('/usuarios/', headers=headers)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_primeiro_usuario_criado_sem_login_vira_admin(client):
    response = client.post('/usuarios/', json=NOVO_USUARIO)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['perfil'] == PerfilUsuario.ADMIN.value


def test_criar_sem_login_apos_bootstrap(client, admin):
    response = client.post('/usuarios/', json=NOVO_USUARIO)

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_admin_cria_usuario(client, admin, token_de):
    response = client.post(
        '/usuarios/', json=NOVO_USUARIO, headers=token_de(admin)
    )

    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['email'] == NOVO_USUARIO['email']
    assert corpo['perfil'] == NOVO_USUARIO['perfil']
    assert 'senha' not in corpo

    salvo = buscar(client, corpo['_id'])
    assert salvo.senha != NOVO_USUARIO['senha']
    assert verify_password(NOVO_USUARIO['senha'], salvo.senha)


@pytest.mark.parametrize('ator', ['gestor', 'membro'])
def test_nao_admin_nao_cria_usuario(client, admin, token_de, request, ator):
    usuario = request.getfixturevalue(ator)

    response = client.post(
        '/usuarios/', json=NOVO_USUARIO, headers=token_de(usuario)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_criar_email_duplicado(client, admin, token_de):
    response = client.post(
        '/usuarios/',
        json={**NOVO_USUARIO, 'email': admin.email},
        headers=token_de(admin),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_listar_usuarios(client, admin, membro, token_de):
    response = client.get('/usuarios/', headers=token_de(membro))

    assert response.status_code == HTTPStatus.OK
    assert {u['email'] for u in response.json()} == {
        admin.email,
        membro.email,
    }


def test_obter_usuario_inexistente(client, membro, token_de):
    response = client.get(
        '/usuarios/000000000000000000000000', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    ('ator', 'alvo', 'esperado'),
    [
        ('admin', 'gestor', HTTPStatus.OK),
        ('admin', 'membro', HTTPStatus.OK),
        ('gestor', 'membro', HTTPStatus.OK),
        ('gestor', 'gestor', HTTPStatus.OK),
        ('gestor', 'admin', HTTPStatus.FORBIDDEN),
        ('membro', 'membro', HTTPStatus.OK),
        ('membro', 'gestor', HTTPStatus.FORBIDDEN),
        ('membro', 'admin', HTTPStatus.FORBIDDEN),
    ],
)
def test_permissao_de_edicao(client, token_de, request, ator, alvo, esperado):
    usuario_ator = request.getfixturevalue(ator)
    usuario_alvo = request.getfixturevalue(alvo)

    response = client.patch(
        f'/usuarios/{usuario_alvo.id}',
        json={'departamento': 'Financeiro'},
        headers=token_de(usuario_ator),
    )

    assert response.status_code == esperado
    salvo = buscar(client, usuario_alvo.id)
    alterado = salvo.departamento == 'Financeiro'
    assert alterado == (esperado == HTTPStatus.OK)


def test_admin_altera_perfil(client, admin, membro, token_de):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'perfil': 'Gestor'},
        headers=token_de(admin),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['perfil'] == 'Gestor'


@pytest.mark.parametrize(
    ('ator', 'alvo'),
    [
        ('gestor', 'membro'),
        ('gestor', 'gestor'),
        ('membro', 'membro'),
    ],
)
def test_nao_admin_nao_altera_perfil(
    client, admin, token_de, request, ator, alvo
):
    usuario_ator = request.getfixturevalue(ator)
    usuario_alvo = request.getfixturevalue(alvo)
    perfil_original = usuario_alvo.perfil

    response = client.patch(
        f'/usuarios/{usuario_alvo.id}',
        json={'perfil': 'Admin'},
        headers=token_de(usuario_ator),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert buscar(client, usuario_alvo.id).perfil == perfil_original


def test_enviar_mesmo_perfil_e_permitido(client, membro, token_de):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'nome': 'Novo Nome', 'perfil': 'Membro'},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK


def test_edicao_parcial_preserva_outros_campos(client, membro, token_de):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'nome': 'Novo Nome', 'email': None},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['nome'] == 'Novo Nome'
    assert corpo['email'] == membro.email
    assert corpo['departamento'] == membro.departamento


def test_editar_para_email_em_uso(client, admin, membro, token_de):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'email': admin.email},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_admin_apaga_usuario(client, admin, membro, token_de):
    response = client.delete(f'/usuarios/{membro.id}', headers=token_de(admin))

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert buscar(client, membro.id) is None


def test_admin_nao_apaga_a_si_mesmo(client, admin, token_de):
    response = client.delete(f'/usuarios/{admin.id}', headers=token_de(admin))

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize('ator', ['gestor', 'membro'])
def test_nao_admin_nao_apaga(client, membro, token_de, request, ator):
    alvo = request.getfixturevalue('criar_usuario')()
    usuario_ator = request.getfixturevalue(ator)

    response = client.delete(
        f'/usuarios/{alvo.id}', headers=token_de(usuario_ator)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert buscar(client, alvo.id) is not None


def test_gestor_alterna_perfil_entre_gestor_e_membro(
    client, gestor, membro, token_de
):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'perfil': 'Gestor'},
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['perfil'] == 'Gestor'


def test_membro_nao_altera_o_proprio_perfil(client, membro, token_de):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'perfil': 'Gestor'},
        headers=token_de(membro),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_alterar_senha(client, admin, membro, token_de):
    response = client.patch(
        f'/usuarios/{membro.id}',
        json={'senha': 'nova-senha-456'},
        headers=token_de(admin),
    )
    assert response.status_code == HTTPStatus.OK
    assert 'senha' not in response.json()

    login = client.post(
        '/auth/token',
        data={'username': membro.email, 'password': 'nova-senha-456'},
    )
    assert login.status_code == HTTPStatus.OK


def test_auth_me_retorna_usuario_logado(client, membro, token_de):
    response = client.get('/auth/me', headers=token_de(membro))
    assert response.status_code == HTTPStatus.OK
    assert response.json()['_id'] == str(membro.id)
    assert response.json()['perfil'] == 'Membro'
