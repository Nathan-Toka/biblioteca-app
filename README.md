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

O modo padrão é apenas para desenvolvimento local. O projeto inclui um Blueprint `render.yaml` para publicar o serviço no Render. Antes de criar o serviço:

1. Envie o código para um repositório privado no GitHub e conecte-o ao Render.
2. Crie um PostgreSQL gerenciado e uma conta Cloudinary. Na configuração inicial do Blueprint, informe a URL interna do banco como `DATABASE_URL` e a URL secreta da conta como `CLOUDINARY_URL`; nunca coloque essas credenciais neste repositório.
3. O Blueprint gera `DJANGO_SECRET_KEY` e define `DJANGO_DEBUG=0`. O comando de publicação instala dependências, coleta arquivos estáticos e aplica migrações.
4. Escolha os planos de hospedagem e banco no Render antes de confirmar a criação; eles podem gerar custos ou ter limitações de disponibilidade. Configure um domínio próprio depois, se desejar.

Em produção, o projeto exige PostgreSQL e Cloudinary, serve arquivos estáticos com WhiteNoise, armazena novas capas no Cloudinary, redireciona HTTP para HTTPS e envia HSTS por um ano. O Render termina TLS no proxy; a aplicação confia no cabeçalho HTTPS do Render e inclui o domínio `onrender.com` na lista de hosts e origens CSRF. Para um domínio próprio, inclua seu domínio em `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` nas variáveis de ambiente do serviço, por exemplo `biblioteca.exemplo.com` e `https://biblioteca.exemplo.com`.

Os dados e capas da instalação local não são copiados automaticamente para os novos serviços: planeje a migração do SQLite e o envio das capas locais antes de abrir o site ao público. Faça e teste backups do banco remoto. Para outros provedores, configure os mesmos requisitos de produção e revise a lista de verificação de implantação do Django.

## Verificações

```powershell
python manage.py check
python manage.py test
```
