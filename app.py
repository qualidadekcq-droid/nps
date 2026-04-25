from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client
from werkzeug.security import generate_password_hash, check_password_hash
import time
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)
# --- FILTRO DE SEGURANÇA ---
from functools import wraps

def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

# --- ROTAS DE ACESSO ---

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('password')
        
        user = supabase.table("usuarios").select("id,nome,senha_hash").eq("email", email).execute()
        
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
        resumo = supabase.table("dashboard_resumo").select("*").single().execute()
        ranking = supabase.table("dashboard_ranking").select("*").single().execute()

        r = resumo.data
        k = ranking.data

        dados = {
            "total_respostas": r["total_respostas"],
            "nps_geral": r["nps_geral"],
            "media_instrutores": f'{r["media_instrutores"]} / 5',
            "media_aplicabilidade": f'{r["media_aplicabilidade"]} / 5',

            "top_instrutor": k["top_instrutor"],
            "top_instrutor_nota": "---",

            "top_treinamento": k["top_treinamento"],
            "pior_treinamento": k["pior_treinamento"],
            "pior_nps": k["pior_nps"]
        }

        return render_template("dashboard.html", **dados)

    except Exception as e:
        return str(e)

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
    resposta = supabase.table("treinamentos").select("id,titulo,instrutor,setor,data_treinamento,status").order("created_at", desc=True).execute()
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
    app.run()
