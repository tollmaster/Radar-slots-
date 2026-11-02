import os, logging, asyncio, threading
from datetime import datetime, timezone
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from db import init_db, is_admin, admins, add_win, check_submission, review_win, radar, recent_wins, casinos, pending_wins, add_campaign, due_campaigns, mark_campaign, stats, unpublished_wins, mark_win_published
from provider_api import poll_official_api

logging.basicConfig(level=logging.INFO)
log=logging.getLogger("radar")
TOKEN=os.environ["BOT_TOKEN"]
CHANNEL=os.environ["CHANNEL_ID"]
WEB_URL=os.getenv("DASHBOARD_PUBLIC_URL","").rstrip("/")
INTERVAL=1800
DISCLAIMER="O ranking reflete relatos enviados e aprovados pela comunidade. Não mede RTP, não indica pagamento em tempo real e não prevê resultados. Resultados passados não garantem resultados futuros."
AGE="🔞 Conteúdo exclusivo para maiores de 18 anos. Aposte com responsabilidade; jogos de azar envolvem risco de perda financeira."

def brl(v): return ("R$ {:,.2f}".format(v)).replace(",","X").replace(".",",").replace("X",".")

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
      "🎰 Radar dos Slots\n\n"
      "/win — enviar relato de ganho\n/slots — ranking 24h\n/ranking — diário, semanal e mensal\n"
      "/casas — plataformas cadastradas\n/ultimos — últimos relatos\n/ajuda — instruções\n\n"
      f"{AGE}")

async def help_cmd(update,context):
    await update.effective_message.reply_text("Use /win no privado: informe slot, aposta, ganho e envie comprovante. Todo relato é moderado antes da publicação. O radar não prevê resultados.")

async def win_cmd(update,context):
    context.user_data["step"]="slot"; context.user_data["data"]={}
    await update.effective_message.reply_text("Qual o nome do slot?")

async def text_input(update,context):
    step=context.user_data.get("step")
    if not step: return
    msg=(update.effective_message.text or "").strip()
    data=context.user_data.setdefault("data",{})
    if step=="slot":
        if len(msg)<2 or len(msg)>80:
            await update.effective_message.reply_text("Nome inválido."); return
        data["slot"]=msg; context.user_data["step"]="bet"
        await update.effective_message.reply_text("Valor apostado? Ex.: 2,50")
    elif step in ("bet","prize"):
        try:
            val=float(msg.replace("R$","").replace(".","").replace(",",".").strip())
            if val<=0 or val>1e8: raise ValueError()
        except ValueError:
            await update.effective_message.reply_text("Valor inválido. Exemplo: 2,50"); return
        if step=="bet":
            data["bet"]=val; context.user_data["step"]="prize"
            await update.effective_message.reply_text("Valor ganho? Ex.: 150,00")
        else:
            data["prize"]=val; context.user_data["step"]="proof"
            await update.effective_message.reply_text("Envie um print do resultado. O comprovante é obrigatório para análise.")

async def proof_input(update,context):
    if context.user_data.get("step")!="proof": return
    photos=update.effective_message.photo
    if not photos:
        await update.effective_message.reply_text("Envie uma foto como comprovante.")
        return
    data=context.user_data["data"]; user=update.effective_user
    flags=check_submission(user.id,data["slot"],data["bet"],data["prize"],photos[-1].file_id)
    wid=add_win(user.id,user.username or user.first_name,data["slot"],data["bet"],data["prize"],photos[-1].file_id,flags)
    context.user_data.clear()
    await update.effective_message.reply_text(f"Recebemos o relato #{wid}. Ele será analisado antes de qualquer publicação.")
    keyboard=InlineKeyboardMarkup([[InlineKeyboardButton("Aprovar",callback_data=f"review:approved:{wid}"),InlineKeyboardButton("Rejeitar",callback_data=f"review:rejected:{wid}")]])
    caption=(f"Relato #{wid}\nSlot: {data['slot']}\nAposta: {brl(data['bet'])}\nGanho: {brl(data['prize'])}\n"
             f"Usuário: {user.id}\nAlertas automáticos: {', '.join(flags) or 'nenhum'}")
    for a in admins():
        try: await context.bot.send_photo(a["telegram_id"],photos[-1].file_id,caption=caption,reply_markup=keyboard)
        except Exception: log.exception("Falha ao notificar admin")

async def review_callback(update,context):
    q=update.callback_query; await q.answer()
    if not is_admin(q.from_user.id):
        await q.edit_message_caption(caption="Ação não autorizada."); return
    _,status,wid=q.data.split(":"); item=review_win(int(wid),status)
    if not item:
        await q.edit_message_caption(caption="Relato já processado ou inexistente."); return
    if status=="approved":
        caption=(f"🎉 RELATO DA COMUNIDADE\n\n🎰 Slot: {item['slot']}\n💵 Aposta informada: {brl(item['bet'])}\n"
                 f"🏆 Ganho informado: {brl(item['prize'])}\n\nRelato submetido por usuário e aprovado pela moderação.\n\n{AGE}\n\n{DISCLAIMER}")
        await context.bot.send_photo(CHANNEL,item["proof_file_id"],caption=caption)
        mark_win_published(int(wid))
        await q.edit_message_caption(caption=f"Relato #{wid} aprovado e publicado.")
    else:
        await q.edit_message_caption(caption=f"Relato #{wid} rejeitado.")

async def ranking_text(period):
    rows=radar(period,10)
    label={"day":"24 HORAS","week":"7 DIAS","month":"30 DIAS"}[period]
    if not rows: return f"🎰 RANKING — {label}\n\nAinda não há relatos aprovados.\n\n{DISCLAIMER}"
    lines=[f"🎰 RANKING — {label}",""]
    for i,r in enumerate(rows,1):
        lines.append(f"{i}. {r['slot']} — {r['wins']} relatos; {brl(r['total_prize'] or 0)} informados")
    lines.extend(["",DISCLAIMER,AGE])
    return "\n".join(lines)

async def slots_cmd(update,context):
    await update.effective_message.reply_text(await ranking_text("day"))

async def ranking_cmd(update,context):
    for period in ("day","week","month"):
        await update.effective_message.reply_text(await ranking_text(period))

async def casas_cmd(update,context):
    rows=casinos()
    if not rows:
        await update.effective_message.reply_text("Nenhuma plataforma cadastrada."); return
    for c in rows:
        url=f"{WEB_URL}/go/{c['id']}" if WEB_URL else c["url"]
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("Acessar plataforma",url=url)]])
        await update.effective_message.reply_text(f"🏠 {c['name']}\n{c['disclosure']}\nPublicidade/afiliado quando aplicável.\n{AGE}",reply_markup=kb)

async def ultimos_cmd(update,context):
    rows=recent_wins(8)
    if not rows:
        await update.effective_message.reply_text("Ainda não há relatos aprovados."); return
    lines=["🧾 ÚLTIMOS RELATOS",""]
    for r in rows: lines.append(f"• {r['slot']} — {brl(r['prize'])} informados")
    lines.extend(["",DISCLAIMER])
    await update.effective_message.reply_text("\n".join(lines))

async def admin_cmd(update,context):
    if not is_admin(update.effective_user.id):
        await update.effective_message.reply_text("Acesso restrito."); return
    s=stats()
    await update.effective_message.reply_text(f"Administração\nPendentes: {s['pending']}\nAprovados: {s['approved']}\nPainel: {WEB_URL or 'Configure DASHBOARD_PUBLIC_URL'}\nComandos: /postar /aviso texto")

async def postar_cmd(update,context):
    if not is_admin(update.effective_user.id): return
    await publish_radar(context)
    await update.effective_message.reply_text("Publicação executada.")

async def aviso_cmd(update,context):
    if not is_admin(update.effective_user.id): return
    body=" ".join(context.args).strip()
    if not body: return
    await context.bot.send_message(CHANNEL,f"📢 COMUNICADO\n\n{body}\n\n{AGE}")

async def publish_radar(context):
    for p in ("day","week","month"):
        await context.bot.send_message(CHANNEL,await ranking_text(p))

async def scheduled_jobs(context):
    # Publica relatos aprovados pelo painel web, se ainda não publicados.
    for item in unpublished_wins():
        try:
            caption=(f"🎉 RELATO DA COMUNIDADE\\n\\n🎰 Slot: {item['slot']}\\n💵 Aposta informada: {brl(item['bet'])}\\n"
                     f"🏆 Ganho informado: {brl(item['prize'])}\\n\\nRelato aprovado pela moderação.\\n\\n{AGE}\\n\\n{DISCLAIMER}")
            if item.get("proof_file_id"):
                await context.bot.send_photo(CHANNEL,item["proof_file_id"],caption=caption)
            else:
                await context.bot.send_message(CHANNEL,caption)
            mark_win_published(item["id"])
        except Exception:
            log.exception("Falha ao publicar relato aprovado pelo painel")
    await publish_radar(context)
    # campanhas com horário UTC; status é marcado após envio
    for camp in due_campaigns():
        try:
            await context.bot.send_message(CHANNEL,f"📢 {camp['title']}\n\n{camp['body']}\n\n{AGE}")
            mark_campaign(camp["id"],"sent")
        except Exception:
            log.exception("Falha ao enviar campanha")
    result=poll_official_api()
    if result["status"]=="error": log.warning("API oficial: %s",result["message"])

async def post_init(app):
    init_db()
    app.job_queue.run_repeating(scheduled_jobs,interval=INTERVAL,first=30,name="radar-30m")

def run_bot():
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("ajuda",help_cmd))
    app.add_handler(CommandHandler("win",win_cmd))
    app.add_handler(CommandHandler("slots",slots_cmd))
    app.add_handler(CommandHandler("ranking",ranking_cmd))
    app.add_handler(CommandHandler("casas",casas_cmd))
    app.add_handler(CommandHandler("ultimos",ultimos_cmd))
    app.add_handler(CommandHandler("admin",admin_cmd))
    app.add_handler(CommandHandler("postar",postar_cmd))
    app.add_handler(CommandHandler("aviso",aviso_cmd))
    app.add_handler(CallbackQueryHandler(review_callback,pattern=r"^review:"))
    app.add_handler(MessageHandler(filters.PHOTO,proof_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_input))
    app.run_polling()

if __name__=="__main__":
    run_bot()
