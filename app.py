from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = 'sua_chave_secreta_muito_segura' # Mude isso!

# Conexão Supabase
supabase: Client = create_client(app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"])

# --- FILTRO DE SEGURANÇA ---
def login_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- ROTAS DE ACESSO ---

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('password')
        
        user = supabase.table("usuarios").select("*").eq("email", email).execute()
        
        if user.data and check_password_hash(user.data[0]['senha_hash'], senha):
            session['user_id'] = user.data[0]['id']
            session['user_nome'] = user.data[0]['nome']
            return redirect(url_for('home'))
        
        flash("E-mail ou senha incorretos.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ROTAS PROTEGIDAS (Adicione @login_required em todas) ---

@app.route("/")
@login_required
def home():
    try:
        # 1. Busca todas as respostas e treinamentos
        resp = supabase.table("respostas").select("nota, instrutor, aplicabilidade, treinamento_id").execute()
        respostas = resp.data
        
        treinos_query = supabase.table("treinamentos").select("id, titulo, instrutor").execute()
        treinos_lista = treinos_query.data
        dict_treinos = {t['id']: t for t in treinos_lista}

        if respostas:
            total_resp = len(respostas)
            
            # Cálculo NPS Geral
            promotores = len([r for r in respostas if r['nota'] >= 9])
            detratores = len([r for r in respostas if r['nota'] <= 6])
            nps_geral = round(((promotores - detratores) / total_resp) * 100)

            # Médias Globais
            media_inst_val = round(sum(r['instrutor'] for r in respostas) / total_resp, 1)
            media_app_val = round(sum(r['aplicabilidade'] for r in respostas) / total_resp, 1)

            # --- Lógica de Ranking para Insights ---
            stats_por_treino = {}
            for r in respostas:
                tid = r['treinamento_id']
                if tid not in stats_por_treino: stats_por_treino[tid] = []
                stats_por_treino[tid].append(r['nota'])

            # Calcula NPS de cada um para achar o melhor e o pior
            ranking = []
            for tid, notas in stats_por_treino.items():
                p = len([n for n in notas if n >= 9])
                d = len([n for n in notas if n <= 6])
                nps_t = round(((p - d) / len(notas)) * 100)
                ranking.append({
                    "titulo": dict_treinos.get(tid, {}).get('titulo', 'Desconhecido'),
                    "nps": nps_t,
                    "instrutor": dict_treinos.get(tid, {}).get('instrutor', 'N/A')
                })

            ranking_ordenado = sorted(ranking, key=lambda x: x['nps'], reverse=True)
            
            top_treino = ranking_ordenado[0]['titulo']
            melhor_inst = ranking_ordenado[0]['instrutor']
            pior_treino = ranking_ordenado[-1]['titulo']
            pior_nps_val = ranking_ordenado[-1]['nps']
        else:
            # Valores padrão caso o banco esteja vazio
            total_resp, nps_geral, media_inst_val, media_app_val = 0, 0, 0, 0
            top_treino, melhor_inst, pior_treino, pior_nps_val = "---", "---", "---", "---"

        dados_painel = {
            "total_respostas": total_resp,
            "nps_geral": nps_geral,
            "media_instrutores": f"{media_inst_val} / 5",
            "media_aplicabilidade": f"{media_app_val} / 5",
            "top_instrutor": melhor_inst,
            "top_instrutor_nota": f"{media_inst_val}/5",
            "top_treinamento": top_treino,
            "pior_treinamento": pior_treino,
            "pior_nps": pior_nps_val
        }
        
        return render_template("dashboard.html", **dados_painel)

    except Exception as e:
        print(f"Erro no Dashboard: {e}")
        return "Erro ao carregar dados. Verifique o console."

@app.route('/cadastrar-treinamento', methods=['POST'])
@login_required # Adicione isso se você quiser que só quem logou possa cadastrar
def cadastrar_treinamento():
    try:
        # Coleta os dados do formulário
        dados = {
            "titulo": request.form.get("titulo"),
            "instrutor": request.form.get("instrutor"),
            "setor": request.form.get("setor"),
            "data_treinamento": request.form.get("data_treinamento"),
            "descricao": request.form.get("descricao"),
            "status": "ativo"
        }
        
        # Insere no Supabase
        supabase.table("treinamentos").insert(dados).execute()
        
        # Após salvar, volta para a lista de treinamentos
        return redirect(url_for('treinamentos'))
        
    except Exception as e:
        print(f"Erro ao cadastrar: {e}")
        return f"Erro interno ao salvar treinamento: {str(e)}", 500


@app.route('/treinamentos')
@login_required
def treinamentos():
    resposta = supabase.table("treinamentos").select("*").order("created_at", desc=True).execute()
    return render_template('treinamentos.html', treinamentos=resposta.data)

@app.route('/participantes')
@login_required
def participantes():
    return render_template('participantes.html', participantes_importados=[])

@app.route('/relatorios')
@login_required
def relatorios():
    # Lógica de feedbacks reais que passamos antes
    return render_template('relatorios.html', feedbacks=[])

# --- ROTAS PÚBLICAS (Alunos não precisam de login) ---

@app.route('/pesquisa')
def pesquisa():
    id_treino = request.args.get('id_treino')
    treino = supabase.table("treinamentos").select("titulo").eq("id", id_treino).single().execute()
    return render_template('feedback_form.html', treinamento_id=id_treino, treinamento_nome=treino.data['titulo'])

@app.route('/salvar-pesquisa', methods=['POST'])
def salvar_pesquisa():
    dados = {
        "treinamento_id": request.form.get('treinamento_id'),
        "nota": int(request.form.get('nota')),
        "comentario": request.form.get('comentario'),
        "clareza": int(request.form.get('clareza', 0)),
        "aplicabilidade": int(request.form.get('aplicabilidade', 0)),
        "instrutor": int(request.form.get('instrutor', 0))
    }
    supabase.table("respostas").insert(dados).execute()
    return "<h1>Obrigado pelo seu feedback!</h1>"

if __name__ == "__main__":
    app.run(debug=True)
