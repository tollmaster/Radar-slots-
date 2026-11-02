import os
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, abort
from db import init_db, admins, add_admin, remove_admin, pending_wins, review_win, radar, casinos, add_casino, delete_casino, click_stats, add_campaign, campaign_list, stats, operator_rows

app=Flask(__name__)
app.secret_key=os.getenv("DASHBOARD_SECRET","change-this-secret-before-deploy")
PASSWORD=os.getenv("DASHBOARD_PASSWORD","")
CHANNEL_ID=os.getenv("CHANNEL_ID","")
init_db()

PAGE=r"""
<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar dos Slots | Admin</title><style>
:root{color-scheme:dark;--bg:#0b0a12;--panel:#171525;--muted:#aaa5bf;--gold:#e6b84c;--line:#302b43}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#282044,var(--bg) 55%);color:#f8f5ff;font:15px system-ui}
main{max-width:1120px;margin:auto;padding:28px 18px}.head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
h1{margin:0;color:var(--gold)}h2{font-size:18px;margin-top:0}.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:22px 0}
.card{background:linear-gradient(145deg,#1c1930,#14121f);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 8px 25px #0003}
.big{font-size:30px;font-weight:750;color:var(--gold)}.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}
input,textarea,select{width:100%;padding:11px;border-radius:9px;border:1px solid var(--line);background:#0e0c17;color:white;margin:5px 0 12px}
button,.btn{display:inline-block;border:0;border-radius:9px;background:var(--gold);color:#191321;padding:10px 14px;font-weight:700;cursor:pointer;text-decoration:none}
.danger{background:#b84b65;color:white}.secondary{background:#373149;color:white}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}small{color:var(--muted)}.flag{color:#ffb6c4}.nav{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.flash{padding:10px;background:#243b30;border-radius:8px;margin:10px 0}
</style></head><body><main>
<div class="head"><div><h1>🎰 Radar dos Slots</h1><div class="muted">Painel administrativo</div></div><a class="btn secondary" href="/logout">Sair</a></div>
{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="flash">{{m}}</div>{% endfor %}{% endwith %}
{% if page=='login' %}
<div class="card" style="max-width:420px;margin:50px auto"><h2>Acesso administrativo</h2><form method="post"><label>Senha do painel</label><input type="password" name="password" required><button>Entrar</button></form></div>
{% else %}
<div class="grid">
{% for label,value in cards %}<div class="card"><div class="muted">{{label}}</div><div class="big">{{value}}</div></div>{% endfor %}
</div>
<div class="nav"><a class="btn secondary" href="#pending">Moderação</a><a class="btn secondary" href="#ranking">Rankings</a><a class="btn secondary" href="#links">Links e cliques</a><a class="btn secondary" href="#campaigns">Campanhas</a><a class="btn secondary" href="#admins">Administradores</a><a class="btn secondary" href="#api">API oficial</a></div>
<div class="cols">
<section class="card" id="pending"><h2>🛡️ Relatos pendentes</h2>
{% if pending %}<table><tr><th>Relato</th><th>Dados</th><th>Ação</th></tr>{% for w in pending %}<tr><td>#{{w.id}}<br>{{w.username}}<br><small>{{w.created_at}}</small></td><td><b>{{w.slot}}</b><br>Aposta R$ {{'%.2f'|format(w.bet)}}<br>Ganho R$ {{'%.2f'|format(w.prize)}}<br><span class="flag">{{w.fraud_flags or 'Sem alertas automáticos'}}</span><br>{% if w.proof_file_id %}<small>Comprovante anexado no Telegram</small>{% else %}<small>Sem comprovante</small>{% endif %}</td><td><form method="post" action="/review/{{w.id}}/approved"><button>Aprovar</button></form><form method="post" action="/review/{{w.id}}/rejected"><button class="danger">Rejeitar</button></form></td></tr>{% endfor %}</table>{% else %}<p class="muted">Nenhum relato pendente.</p>{% endif %}</section>
<section class="card" id="ranking"><h2>📊 Rankings da comunidade</h2>
{% for period,label in [('day','24 horas'),('week','7 dias'),('month','30 dias')] %}<h3>{{label}}</h3><ol>{% for r in rankings[period] %}<li>{{r.slot}} — {{r.wins}} relatos, R$ {{'%.2f'|format(r.total_prize or 0)}} informados</li>{% else %}<li class="muted">Sem dados</li>{% endfor %}</ol>{% endfor %}
<p><small>Ranking de relatos aprovados, não RTP nem previsão de pagamento.</small></p></section>
<section class="card" id="links"><h2>🔗 Plataformas e cliques</h2><form method="post" action="/casino"><label>Nome</label><input name="name" required><label>URL completa</label><input name="url" placeholder="https://..." required><label>Identificação comercial</label><input name="disclosure" value="Publicidade/afiliado"><button>Cadastrar link</button></form>
<table><tr><th>Plataforma</th><th>Cliques</th><th>Únicos</th><th>Ação</th></tr>{% for c in clicks %}<tr><td>{{c.name}}<br><small>/go/{{c.id}}</small></td><td>{{c.clicks}}</td><td>{{c.unique_users}}</td><td><form method="post" action="/casino/{{c.id}}/delete"><button class="danger">Excluir</button></form></td></tr>{% endfor %}</table></section>
<section class="card" id="campaigns"><h2>📣 Campanhas agendadas</h2><form method="post" action="/campaign"><label>Título</label><input name="title" required><label>Mensagem</label><textarea name="body" rows="4" required></textarea><label>Data/hora ISO 8601 (UTC), ex.: 2026-11-03T18:00:00+00:00</label><input name="run_at" placeholder="2026-11-03T18:00:00+00:00" required><button>Agendar</button></form>
<table><tr><th>Campanha</th><th>Execução</th><th>Status</th></tr>{% for c in campaigns %}<tr><td>{{c.title}}</td><td>{{c.run_at}}</td><td>{{c.status}}</td></tr>{% endfor %}</table></section>
<section class="card" id="admins"><h2>👥 Administradores Telegram</h2><form method="post" action="/admin/add"><label>ID numérico Telegram</label><input name="telegram_id" type="number" required><label>Identificação</label><input name="label" value="Administrador"><button>Adicionar</button></form>
<table>{% for a in admins %}<tr><td>{{a.telegram_id}}<br><small>{{a.label}}</small></td><td><form method="post" action="/admin/{{a.telegram_id}}/remove"><button class="danger">Remover</button></form></td></tr>{% endfor %}</table></section>
<section class="card" id="api"><h2>🔌 Integração com API oficial</h2><p class="muted">A API só será consultada se você tiver URL, documentação e autorização da operadora. Configure OPERATORS_API_URL e OPERATORS_API_TOKEN no serviço. O formato esperado está no README.</p>
{% for r in operator_rows %}<p>{{r.operator}} / {{r.slot}} — {{r.metric_name}}: {{r.metric_value}}<br><small>{{r.observed_at}} · {{r.source}}</small></p>{% else %}<p class="muted">Nenhuma fonte oficial configurada ou dado recebido.</p>{% endfor %}</section>
</div>
{% endif %}
</main></body></html>
"""

def login_required(fn):
    @wraps(fn)
    def wrapped(*a,**k):
        if not session.get("ok"): return redirect(url_for("index"))
        return fn(*a,**k)
    return wrapped

@app.route("/",methods=["GET","POST"])
def index():
    if request.method=="POST":
        if PASSWORD and request.form.get("password")==PASSWORD:
            session["ok"]=True
            return redirect("/")
        return render_template_string(PAGE,page="login"),401
    if not session.get("ok"): return render_template_string(PAGE,page="login")
    s=stats()
    cards=[("Usuários",s["users"]),("Relatos aprovados",s["approved"]),("Pendentes",s["pending"]),("Rejeitados",s["rejected"]),("Cliques rastreados",s["clicks"]),("Campanhas agendadas",s["campaigns"])]
    return render_template_string(PAGE,page="home",cards=cards,pending=pending_wins(),rankings={"day":radar("day"),"week":radar("week"),"month":radar("month")},clicks=click_stats(),campaigns=campaign_list(),admins=admins(),operator_rows=operator_rows())

@app.route("/logout")
def logout():
    session.clear(); return redirect("/")

@app.route("/review/<int:wid>/<status>",methods=["POST"])
@login_required
def review(wid,status):
    if status not in ("approved","rejected"): abort(400)
    review_win(wid,status)
    return redirect("/#pending")

@app.route("/admin/add",methods=["POST"])
@login_required
def admin_add():
    try: add_admin(int(request.form["telegram_id"]),request.form.get("label","Administrador")[:80])
    except Exception: pass
    return redirect("/#admins")

@app.route("/admin/<int:uid>/remove",methods=["POST"])
@login_required
def admin_remove(uid):
    remove_admin(uid); return redirect("/#admins")

@app.route("/casino",methods=["POST"])
@login_required
def casino_add():
    from urllib.parse import urlparse
    url=request.form["url"].strip()
    if urlparse(url).scheme not in ("http","https") or not urlparse(url).netloc: abort(400)
    add_casino(request.form["name"][:100],url,request.form.get("disclosure","Publicidade/afiliado")[:150])
    return redirect("/#links")

@app.route("/casino/<int:cid>/delete",methods=["POST"])
@login_required
def casino_delete(cid):
    delete_casino(cid); return redirect("/#links")

@app.route("/campaign",methods=["POST"])
@login_required
def campaign_add():
    from datetime import datetime, timezone
    raw=request.form["run_at"].strip()
    try:
        dt=datetime.fromisoformat(raw)
        if dt.tzinfo is None: abort(400)
        if dt.astimezone(timezone.utc) < datetime.now(timezone.utc): abort(400)
    except ValueError: abort(400)
    add_campaign(request.form["title"][:120],request.form["body"][:3500],dt.astimezone(timezone.utc).isoformat(),0)
    return redirect("/#campaigns")

@app.route("/go/<int:cid>")
def go(cid):
    from flask import make_response
    target=None
    for c in casinos():
        if c["id"]==cid: target=c["url"]; break
    if not target: abort(404)
    uid=request.args.get("uid")
    try: uid=int(uid) if uid else None
    except ValueError: uid=None
    add_click(cid,uid)
    return redirect(target,code=302)
