from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import time
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True   # se usa HTTPS
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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
@app.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual")
        nova_senha = request.form.get("nova_senha")
        confirmar = request.form.get("confirmar")

        user_id = session["user_id"]

        usuario = supabase.table("usuarios")\
            .select("senha_hash")\
            .eq("id", user_id)\
            .single()\
            .execute()

        hash_salvo = usuario.data["senha_hash"]

        # valida senha atual
        if not check_password_hash(hash_salvo, senha_atual):
            flash("Senha atual incorreta.")
            return redirect(url_for("trocar_senha"))

        # confirma nova senha
        if nova_senha != confirmar:
            flash("As novas senhas não conferem.")
            return redirect(url_for("trocar_senha"))

        # tamanho mínimo
        if len(nova_senha) < 6:
            flash("Nova senha muito curta.")
            return redirect(url_for("trocar_senha"))

        novo_hash = generate_password_hash(nova_senha)

        supabase.table("usuarios").update({
            "senha_hash": novo_hash
        }).eq("id", user_id).execute()

        flash("Senha alterada com sucesso.")
        return redirect(url_for("home"))

    return render_template("trocar_senha.html")

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

@app.route('/importar-presenca', methods=['POST'])
@login_required
def importar_presenca():
    try:
        arquivo = request.files.get("file")

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo.")
            return redirect(url_for("participantes"))

        nome = arquivo.filename.lower()

        # Detecta tipo de arquivo
        if nome.endswith(".csv"):
            df = pd.read_csv(arquivo)

        elif nome.endswith(".xlsx"):
            df = pd.read_excel(arquivo, engine="openpyxl")

        elif nome.endswith(".xls"):
            df = pd.read_excel(arquivo, engine="xlrd")

        elif nome.endswith(".ods"):
            df = pd.read_excel(arquivo, engine="odf")

        else:
            flash("Formato não suportado. Use XLSX, XLS, CSV ou ODS.")
            return redirect(url_for("participantes"))

        participantes = []

        for _, row in df.iterrows():
            nome = str(row.iloc[0]).strip() if len(row) > 0 else ""
            tema = str(row.iloc[1]).strip() if len(row) > 1 else ""
            whatsapp = str(row.iloc[2]).strip() if len(row) > 2 else ""

            if nome and nome != "nan":
                participantes.append({
                    "nome": nome,
                    "tema": "" if tema == "nan" else tema,
                    "whatsapp": "" if whatsapp == "nan" else whatsapp
                })

        return render_template(
            "participantes.html",
            participantes_importados=participantes
        )

    except Exception as e:
        return f"Erro ao importar planilha: {str(e)}"


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
   app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
