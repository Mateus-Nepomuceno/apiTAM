from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from tam.tarefa.models import PrioridadeTarefa, StatusTarefa, TarefaModel


def buscar(client, tarefa_id):
    return client.portal.call(TarefaModel.get, tarefa_id)


def test_criar_tarefa_nao_autenticado(client):
    payload = {
        'titulo': 'Tarefa Sem Auth',
        'descricao': 'Tentativa sem token',
    }
    response = client.post('/tarefas/', json=payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_membro_cria_tarefa_com_sucesso(client, membro, token_de):
    agora = datetime.now(timezone.utc)
    payload = {
        'titulo': 'Tarefa do Membro',
        'descricao': 'Criada pelo membro da equipe',
        'status': 'Pendente',
        'prioridade': 'Media',
        'etiquetas': ['backend', 'bug'],
        'data_inicio': agora.isoformat(),
        'data_prazo': (agora + timedelta(days=5)).isoformat(),
    }
    response = client.post('/tarefas/', json=payload, headers=token_de(membro))
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['titulo'] == payload['titulo']
    assert corpo['status'] == StatusTarefa.PENDENTE.value
    assert corpo['prioridade'] == PrioridadeTarefa.MEDIA.value
    assert corpo['criador_id'] == str(membro.id)
    assert 'backend' in corpo['etiquetas']

    salvo = buscar(client, corpo['_id'])
    assert salvo is not None
    assert salvo.titulo == payload['titulo']


def test_gestor_cria_tarefa_com_sucesso(client, gestor, token_de):
    payload = {
        'titulo': 'Planejar sprint',
        'descricao': 'Definir metas da semana',
        'prioridade': 'Alta',
    }
    response = client.post('/tarefas/', json=payload, headers=token_de(gestor))
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['titulo'] == payload['titulo']
    assert corpo['prioridade'] == PrioridadeTarefa.ALTA.value
    assert corpo['criador_id'] == str(gestor.id)


def test_admin_cria_tarefa_com_sucesso(client, admin, token_de):
    payload = {
        'titulo': 'Auditoria de segurança',
        'descricao': 'Revisão periódica',
        'prioridade': 'Urgente',
    }
    response = client.post('/tarefas/', json=payload, headers=token_de(admin))
    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['titulo'] == payload['titulo']


def test_criar_tarefa_com_projeto_e_responsavel(
    client, gestor, membro, criar_projeto, token_de
):
    projeto = criar_projeto(responsavel=gestor)
    payload = {
        'titulo': 'Implementar autenticação JWT',
        'descricao': 'Configurar rotas e tokens',
        'projeto_id': str(projeto.id),
        'responsavel_id': str(membro.id),
        'prioridade': 'Alta',
    }
    response = client.post('/tarefas/', json=payload, headers=token_de(gestor))
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['projeto_id'] == str(projeto.id)
    assert corpo['responsavel_id'] == str(membro.id)


def test_criar_tarefa_com_checklist(client, membro, token_de):
    payload = {
        'titulo': 'Preparar deploy',
        'descricao': 'Checklist de validação',
        'checklist': [
            {'titulo': 'Rodar testes unitários', 'concluido': True},
            {'titulo': 'Verificar variáveis de ambiente', 'concluido': False},
        ],
    }
    response = client.post('/tarefas/', json=payload, headers=token_de(membro))
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    qtd_checklist = 2
    assert len(corpo['checklist']) == qtd_checklist
    assert corpo['checklist'][0]['titulo'] == 'Rodar testes unitários'
    assert corpo['checklist'][0]['concluido'] is True
    assert corpo['checklist'][1]['concluido'] is False
    assert corpo['checklist'][0]['id']


def test_criar_tarefa_com_data_prazo_anterior_ao_inicio(
    client, gestor, token_de
):
    agora = datetime.now(timezone.utc)
    payload = {
        'titulo': 'Tarefa Inválida',
        'descricao': 'Datas inconsistentes',
        'data_inicio': agora.isoformat(),
        'data_prazo': (agora - timedelta(days=2)).isoformat(),
    }
    response = client.post('/tarefas/', json=payload, headers=token_de(gestor))
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_listar_tarefas_autenticado(client, criar_tarefa, membro, token_de):
    qtd_tarefas = 2
    criar_tarefa(titulo='Tarefa 1')
    criar_tarefa(titulo='Tarefa 2')

    response = client.get('/tarefas/', headers=token_de(membro))
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert len(corpo) >= qtd_tarefas


def test_listar_tarefas_com_filtro_status(
    client, criar_tarefa, gestor, token_de
):
    criar_tarefa(titulo='Em Andamento', status=StatusTarefa.EM_ANDAMENTO)
    criar_tarefa(titulo='Concluida 1', status=StatusTarefa.CONCLUIDA)

    response = client.get(
        '/tarefas/?status=EmAndamento', headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert all(t['status'] == StatusTarefa.EM_ANDAMENTO.value for t in corpo)
    assert any(t['titulo'] == 'Em Andamento' for t in corpo)
    assert not any(t['titulo'] == 'Concluida 1' for t in corpo)


def test_listar_tarefas_com_filtro_prioridade(
    client, criar_tarefa, admin, token_de
):
    criar_tarefa(titulo='Critica', prioridade=PrioridadeTarefa.URGENTE)
    criar_tarefa(titulo='Normal', prioridade=PrioridadeTarefa.BAIXA)

    response = client.get(
        '/tarefas/?prioridade=Urgente', headers=token_de(admin)
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert all(
        t['prioridade'] == PrioridadeTarefa.URGENTE.value for t in corpo
    )
    assert any(t['titulo'] == 'Critica' for t in corpo)
    assert not any(t['titulo'] == 'Normal' for t in corpo)


def test_listar_tarefas_com_filtro_projeto(
    client, criar_tarefa, criar_projeto, membro, token_de
):
    projeto = criar_projeto()
    criar_tarefa(titulo='Tarefa do Projeto', projeto_id=projeto.id)
    criar_tarefa(titulo='Tarefa Avulsa', projeto_id=None)

    response = client.get(
        f'/tarefas/?projeto_id={projeto.id}', headers=token_de(membro)
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert all(t['projeto_id'] == str(projeto.id) for t in corpo)
    assert any(t['titulo'] == 'Tarefa do Projeto' for t in corpo)
    assert not any(t['titulo'] == 'Tarefa Avulsa' for t in corpo)


def test_listar_tarefas_com_filtro_responsavel(
    client, criar_tarefa, gestor, membro, token_de
):
    criar_tarefa(titulo='Para Membro', responsavel=membro)
    criar_tarefa(titulo='Para Gestor', responsavel=gestor)

    response = client.get(
        f'/tarefas/?responsavel_id={membro.id}', headers=token_de(membro)
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert all(t['responsavel_id'] == str(membro.id) for t in corpo)
    assert any(t['titulo'] == 'Para Membro' for t in corpo)


def test_listar_tarefas_com_filtro_etiqueta(
    client, criar_tarefa, membro, token_de
):
    criar_tarefa(titulo='Frontend UI', etiquetas=['frontend', 'design'])
    criar_tarefa(titulo='Banco de Dados', etiquetas=['database'])

    response = client.get(
        '/tarefas/?etiqueta=frontend', headers=token_de(membro)
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert any(t['titulo'] == 'Frontend UI' for t in corpo)
    assert not any(t['titulo'] == 'Banco de Dados' for t in corpo)


def test_obter_tarefa_por_id_existente(client, criar_tarefa, membro, token_de):
    tarefa = criar_tarefa(titulo='Tarefa Encontrada')

    response = client.get(f'/tarefas/{tarefa.id}', headers=token_de(membro))
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['_id'] == str(tarefa.id)
    assert corpo['titulo'] == 'Tarefa Encontrada'


def test_obter_tarefa_por_id_inexistente(client, membro, token_de):
    response = client.get(
        '/tarefas/000000000000000000000000', headers=token_de(membro)
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_transicao_de_status_acumula_historico_e_data_conclusao(
    client, criar_tarefa, gestor, token_de
):
    tarefa = criar_tarefa(
        titulo='Tarefa em Fluxo', status=StatusTarefa.PENDENTE
    )

    response = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'status': 'EmAndamento'},
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['status'] == StatusTarefa.EM_ANDAMENTO.value
    assert len(corpo['historico_status']) == 1

    historico = corpo['historico_status'][0]
    assert historico['status_anterior'] == StatusTarefa.PENDENTE.value
    assert historico['status_novo'] == StatusTarefa.EM_ANDAMENTO.value
    assert historico['autor_id'] == str(gestor.id)

    # Concluindo a tarefa
    resp_concluida = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'status': 'Concluida'},
        headers=token_de(gestor),
    )
    assert resp_concluida.status_code == HTTPStatus.OK
    corpo_concluida = resp_concluida.json()
    assert corpo_concluida['status'] == StatusTarefa.CONCLUIDA.value
    assert corpo_concluida['data_conclusao'] is not None
    qtd_historico = 2
    assert len(corpo_concluida['historico_status']) == qtd_historico


def test_atualizar_tarefa_com_data_prazo_anterior_ao_inicio(
    client, criar_tarefa, gestor, token_de
):
    tarefa = criar_tarefa()
    response = client.patch(
        f'/tarefas/{tarefa.id}',
        json={
            'data_prazo': (tarefa.data_inicio - timedelta(days=2)).isoformat()
        },
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_membro_criador_atualiza_sua_tarefa(
    client, criar_tarefa, membro, token_de
):
    tarefa = criar_tarefa(criador=membro, titulo='Original')

    response = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'titulo': 'Titulo Atualizado'},
        headers=token_de(membro),
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['titulo'] == 'Titulo Atualizado'


def test_membro_responsavel_atualiza_tarefa_atribuida(
    client, criar_tarefa, admin, membro, token_de
):
    tarefa = criar_tarefa(criador=admin, responsavel=membro)

    response = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'status': 'EmAndamento'},
        headers=token_de(membro),
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['status'] == StatusTarefa.EM_ANDAMENTO.value


def test_membro_nao_atualiza_tarefa_alheia(
    client, criar_tarefa, admin, membro, criar_usuario, token_de
):
    outro_membro = criar_usuario(nome='Outro Membro', email='outro@test.com')
    tarefa = criar_tarefa(criador=admin, responsavel=outro_membro)

    response = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'titulo': 'Hacked'},
        headers=token_de(membro),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_gestor_e_admin_atualizam_qualquer_tarefa(
    client, criar_tarefa, membro, gestor, admin, token_de
):
    tarefa = criar_tarefa(criador=membro)

    # Gestor atualiza
    res_gestor = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'descricao': 'Alterado por Gestor'},
        headers=token_de(gestor),
    )
    assert res_gestor.status_code == HTTPStatus.OK

    # Admin atualiza
    res_admin = client.patch(
        f'/tarefas/{tarefa.id}',
        json={'descricao': 'Alterado por Admin'},
        headers=token_de(admin),
    )
    assert res_admin.status_code == HTTPStatus.OK


def test_atualizar_tarefa_inexistente(client, gestor, token_de):
    response = client.patch(
        '/tarefas/000000000000000000000000',
        json={'titulo': 'Nao Existe'},
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_membro_apaga_sua_propria_tarefa(
    client, criar_tarefa, membro, token_de
):
    tarefa = criar_tarefa(criador=membro)

    response = client.delete(f'/tarefas/{tarefa.id}', headers=token_de(membro))
    assert response.status_code == HTTPStatus.NO_CONTENT

    salvo = buscar(client, tarefa.id)
    assert salvo is None


def test_membro_nao_apaga_tarefa_de_outro(
    client, criar_tarefa, admin, membro, token_de
):
    tarefa = criar_tarefa(criador=admin)

    response = client.delete(f'/tarefas/{tarefa.id}', headers=token_de(membro))
    assert response.status_code == HTTPStatus.FORBIDDEN

    salvo = buscar(client, tarefa.id)
    assert salvo is not None


def test_gestor_e_admin_apagam_qualquer_tarefa(
    client, criar_tarefa, membro, gestor, admin, token_de
):
    tarefa1 = criar_tarefa(criador=membro)
    tarefa2 = criar_tarefa(criador=membro)

    res_gestor = client.delete(
        f'/tarefas/{tarefa1.id}', headers=token_de(gestor)
    )
    assert res_gestor.status_code == HTTPStatus.NO_CONTENT

    res_admin = client.delete(
        f'/tarefas/{tarefa2.id}', headers=token_de(admin)
    )
    assert res_admin.status_code == HTTPStatus.NO_CONTENT


def test_apagar_tarefa_inexistente(client, gestor, token_de):
    response = client.delete(
        '/tarefas/000000000000000000000000', headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_adicionar_comentario_na_tarefa(
    client, criar_tarefa, membro, token_de
):
    tarefa = criar_tarefa()

    response = client.post(
        f'/tarefas/{tarefa.id}/comentarios',
        json={'texto': 'Primeiro comentário sobre a entrega'},
        headers=token_de(membro),
    )
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert len(corpo['comentarios']) == 1
    assert corpo['comentarios'][0]['texto'] == (
        'Primeiro comentário sobre a entrega'
    )
    assert corpo['comentarios'][0]['autor_id'] == str(membro.id)


def test_atualizar_com_novo_comentario_e_checklist(
    client, criar_tarefa, gestor, token_de
):
    tarefa = criar_tarefa()

    payload = {
        'novo_comentario': 'Atualização de progresso pelo gestor',
        'checklist': [
            {'titulo': 'Item 1', 'concluido': True},
        ],
    }
    response = client.patch(
        f'/tarefas/{tarefa.id}',
        json=payload,
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert len(corpo['comentarios']) == 1
    assert corpo['comentarios'][0]['texto'] == (
        'Atualização de progresso pelo gestor'
    )
    assert len(corpo['checklist']) == 1
    assert corpo['checklist'][0]['concluido'] is True
