"""Adapter opcional para API oficial contratada/autorizada pela operadora.

Defina OPERATORS_API_URL e OPERATORS_API_TOKEN somente se tiver documentação e
permissão de acesso. O endpoint deve retornar JSON no formato:
{"data":[{"operator":"Operadora","slot":"Nome do jogo",
"metric_name":"RTP publicado","metric_value":"96.2%"}]}

Não faz scraping, não tenta descobrir endpoints privados e não interpreta RTP
como previsão de ganhos. Se a API não estiver configurada, não há dado ao vivo.
"""
import os, json, urllib.request
from db import save_operator_rows

def poll_official_api():
    url=os.getenv("OPERATORS_API_URL","").strip()
    token=os.getenv("OPERATORS_API_TOKEN","").strip()
    if not url:
        return {"status":"not_configured","message":"Nenhuma API oficial configurada."}
    req=urllib.request.Request(url,headers={"Accept":"application/json"})
    if token:
        req.add_header("Authorization",f"Bearer {token}")
    try:
        with urllib.request.urlopen(req,timeout=12) as response:
            payload=json.loads(response.read().decode("utf-8"))
        rows=payload.get("data",[])
        valid=[]
        for row in rows:
            required=("operator","slot","metric_name","metric_value")
            if all(k in row for k in required):
                valid.append({k:str(row[k])[:200] for k in required})
        save_operator_rows(valid)
        return {"status":"ok","count":len(valid)}
    except Exception as exc:
        return {"status":"error","message":str(exc)[:300]}
