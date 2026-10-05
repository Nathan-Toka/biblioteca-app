# Biblioteca escolar

Aplicativo web escolar feito em Python e Django. Leitores podem criar uma conta, pesquisar o acervo, solicitar empréstimos e consultar prazos. A administração mantém os livros, os exemplares e os empréstimos presenciais.

## Requisitos

- Python 3.10 ou mais recente
- PowerShell no Windows

## Preparar e iniciar no Windows

Na pasta do projeto, execute:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abra `http://127.0.0.1:8000/` para leitores e `http://127.0.0.1:8000/gestao/` para a administração. O primeiro administrador é criado interativamente pelo comando `createsuperuser`; não há conta ou senha padrão.

Os dados ficam no arquivo SQLite `db.sqlite3`, criado no projeto após as migrações. No primeiro uso, uma chave aleatória para desenvolvimento é gerada em `.django_secret_key`, que não deve ser compartilhada ou versionada.

## Fluxo de uso

1. O leitor pesquisa o catálogo e pode abrir os detalhes de um livro para consultar descrição, categoria, localização e disponibilidade. Depois de criar uma conta e entrar, pode solicitar um livro disponível; a confirmação é imediata e o prazo é de 30 dias.
2. Em **Meus empréstimos**, o leitor vê avisos para devoluções atrasadas e para empréstimos que vencem hoje ou nos próximos 7 dias.
3. Em **Minha conta**, o leitor pode atualizar nome, sobrenome e e-mail, além de alterar a senha confirmando a senha atual. O nome de usuário não pode ser alterado nessa página.
4. A página de detalhes mostra a descrição completa do livro ao lado da capa.
5. Na página do livro, leitores conectados podem publicar uma avaliação de 1 a 5 estrelas e um comentário de até 2.000 caracteres. Cada leitor pode avaliar cada livro uma vez e editar sua própria avaliação; a média e as opiniões ficam visíveis para todos.
6. Se não houver exemplar, a página informa a indisponibilidade e orienta o leitor a conversar com o administrador presencialmente; o sistema não cria fila.
7. O administrador cadastra/edita livros em **Gestão > Livros**. Além de controlar o acervo, pode enviar uma capa JPG, PNG ou WebP de até 5 MB. As imagens enviadas ficam na pasta local `media\capas\`.
8. Para registrar uma entrega física, o administrador usa **Gestão > Empréstimos > Registrar entrega presencial** e seleciona leitor e livro.
9. Para registrar uma devolução antecipada, use **Gestão > Empréstimos > Registrar entrega presencial**, selecione o empréstimo ativo na seção **Registrar devolução antecipada** e confirme. Também é possível registrar devoluções pela ação em massa na lista de empréstimos. A disponibilidade é atualizada uma única vez; o livro pode então ser entregue a outro leitor ou voltar à prateleira.
10. Para acompanhar os resultados, acesse **Gestão > Relatórios de empréstimos**. Filtre por leitor/livro, situação e período de empréstimo; use **Exportar resultados CSV** para baixar os resultados encontrados. O relatório é restrito a administradores com permissão de visualização de empréstimos.

Após atualizar o projeto, execute `python manage.py migrate` para criar ou atualizar o banco de dados. Os livros já cadastrados permanecem sem capa até o administrador adicionar uma imagem e sem avaliações até leitores começarem a avaliá-los.

## Configuração para publicação

O modo padrão é apenas para desenvolvimento local. Antes de publicar, configure `DJANGO_DEBUG=0`, defina `DJANGO_SECRET_KEY` com um segredo aleatório fora do código e restrinja `DJANGO_ALLOWED_HOSTS` aos domínios reais. Com `DJANGO_DEBUG=0`, o Django redireciona requisições HTTP para HTTPS e envia uma política HSTS de um ano nas respostas HTTPS. Portanto, configure e teste o certificado TLS no servidor ou proxy antes de ativar esse modo; se houver um proxy que termina TLS, configure-o para encaminhar corretamente o protocolo HTTPS ao Django. Configure o serviço de publicação para servir os arquivos de mídia enviados (a configuração local `MEDIA_ROOT` não serve mídias em produção). Revise a lista de verificação de implantação do Django. Para publicação com múltiplos usuários simultâneos, substitua o SQLite por PostgreSQL e configure o banco fora do código.

## Verificações

```powershell
python manage.py check
python manage.py test
```
