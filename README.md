# Radar dos Slots v2 — canal + painel visual

## Funcionalidades
- Bot Telegram para canal, com `/win` e aprovação manual de relatos.
- Painel web responsivo: moderação, admins, links, campanhas, ranking e métricas.
- Múltiplos administradores com IDs Telegram.
- Proteções antifraude: comprovante obrigatório, limite de 5 envios/dia, intervalo mínimo de 90s, detecção de repetição e alertas para multiplicadores extremos.
- Rankings 24h, 7 dias e 30 dias.
- Campanhas agendadas pelo painel (horário ISO 8601 com fuso).
- Cliques registrados por redirecionador `/go/ID`.
- Consulta opcional de API oficial documentada e autorizada.
- Atualização/publicação do radar a cada 30 minutos.

## Limites e transparência
O sistema não identifica “slot que está pagando mais” em tempo real por conta própria. O ranking comunitário usa relatos aprovados, não RTP, não probabilidade e não previsão. API oficial só funciona se a operadora fornecer acesso autorizado e documentação. Não use scraping ou endpoints privados.
Os alertas antifraude são sinais para revisão humana, não prova de fraude. A aprovação manual continua necessária.

## Configuração local
Python 3.11+:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
Preencha as variáveis. Inicie bot e painel juntos:
```bash
set -a; source .env; set +a
python app/main.py
```
Abra `http://localhost:8000`. O primeiro acesso usa `DASHBOARD_PASSWORD`.

## Telegram
1. Crie o bot em @BotFather e copie o token.
2. Crie o canal e adicione o bot como administrador com permissão de publicar.
3. Configure `CHANNEL_ID` como `@username` ou ID `-100...`.
4. Informe os IDs Telegram iniciais em `ADMIN_IDS`, separados por vírgula.
5. Para cadastrar mais admins, use o painel. O admin novo passa a poder aprovar/rejeitar relatos no Telegram.

## Render
1. Envie o projeto para um repositório privado no GitHub.
2. No Render, selecione **New > Blueprint** e conecte o repositório.
3. Configure `BOT_TOKEN`, `CHANNEL_ID`, `ADMIN_IDS`, `DASHBOARD_PASSWORD` e `DASHBOARD_PUBLIC_URL`.
4. O blueprint cria um único serviço web que executa o painel e o bot no mesmo processo, compartilhando o mesmo SQLite em disco persistente.
5. Aguarde o deploy e abra o endereço do serviço para acessar o painel.

O plano de hospedagem precisa oferecer disco persistente. Não execute múltiplas réplicas desse serviço com SQLite; para escalar, migre para PostgreSQL e separe bot e painel.

## API oficial
Configure somente endpoint oficial/autorizado. O adaptador espera:
```json
{
  "data": [
    {
      "operator": "Operadora",
      "slot": "Nome do jogo",
      "metric_name": "RTP publicado",
      "metric_value": "96.2%"
    }
  ]
}
```
Os valores são armazenados como snapshots com data/hora e fonte. RTP teórico/publicado não significa pagamento ao vivo nem previsão de resultado. Confirme com a documentação do fornecedor a frequência permitida e os limites de chamadas.

## Segurança e privacidade
- Use HTTPS no painel, senha forte e segredo de sessão aleatório.
- Nunca publique token do bot, senhas ou tokens de API no GitHub.
- Limite acesso do painel; para produção, adicione MFA/SSO e proteção contra tentativas de login.
- Evite dados pessoais nos comprovantes e defina prazo de retenção.
- Cumpra LGPD, regras de publicidade, normas brasileiras aplicáveis, regras do Telegram e restrição 18+.
- Identifique links comerciais/afiliados e não prometa ganhos.
