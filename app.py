from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from supabase import create_client
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from functools import wraps
import pandas as pd
import time
import os
import io

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# =========================
# SUPABASE
# =========================
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# =========================
# LOGIN REQUIRED
# =========================
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap


# ==========================================================
# LOGIN / LOGOUT
# ==========================================================
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        senha = request.form.get("password")

        user = supabase.table("usuarios") \
            .select("id,nome,senha_hash") \
            .eq("email", email) \
            .execute()

        if user.data:
            if check_password_hash(user.data[0]["senha_hash"], senha):
                session["user_id"] = user.data[0]["id"]
                session["user_nome"] = user.data[0]["nome"]
                return redirect(url_for("home"))

        flash("E-mail ou senha incorretos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================================================
# TROCAR SENHA
# ==========================================================
@app.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():

    if request.method == "POST":

        senha_atual = request.form.get("senha_atual")
        nova_senha = request.form.get("nova_senha")
        confirmar = request.form.get("confirmar")

        user_id = session["user_id"]

        usuario = supabase.table("usuarios") \
            .select("senha_hash") \
            .eq("id", user_id) \
            .single() \
            .execute()

        hash_salvo = usuario.data["senha_hash"]

        if not check_password_hash(hash_salvo, senha_atual):
            flash("Senha atual incorreta.")
            return redirect(url_for("trocar_senha"))

        if nova_senha != confirmar:
            flash("As novas senhas não conferem.")
            return redirect(url_for("trocar_senha"))

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


# ==========================================================
# DASHBOARD
# ==========================================================
@app.route("/")
@login_required
def home():

    try:
        resumo = supabase.table("dashboard_resumo") \
            .select("*") \
            .single() \
            .execute()

        ranking = supabase.table("dashboard_ranking") \
            .select("*") \
            .single() \
            .execute()

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


# ==========================================================
# TREINAMENTOS
# ==========================================================
@app.route("/cadastrar-treinamento", methods=["POST"])
@login_required
def cadastrar_treinamento():

    try:
        dados = {
            "titulo": request.form.get("titulo"),
            "instrutor": request.form.get("instrutor"),
            "setor": request.form.get("setor"),
            "data_treinamento": request.form.get("data_treinamento"),
            "descricao": request.form.get("descricao"),
            "status": "ativo"
        }

        supabase.table("treinamentos").insert(dados).execute()

        return redirect(url_for("treinamentos"))

    except Exception as e:
        return f"Erro interno ao salvar treinamento: {str(e)}", 500


@app.route("/treinamentos")
@login_required
def treinamentos():

    resposta = supabase.table("treinamentos") \
        .select("id,titulo,instrutor,setor,data_treinamento,status") \
        .order("created_at", desc=True) \
        .execute()

    return render_template(
        "treinamentos.html",
        treinamentos=resposta.data
    )


# ==========================================================
# PARTICIPANTES
# ==========================================================
@app.route("/participantes")
@login_required
def participantes():
    return render_template(
        "participantes.html",
        participantes_importados=[]
    )


@app.route("/importar-presenca", methods=["POST"])
@login_required
def importar_presenca():

    try:
        arquivo = request.files.get("file")

        if not arquivo or arquivo.filename == "":
            flash("Selecione um arquivo.")
            return redirect(url_for("participantes"))

        nome = arquivo.filename.lower()

        if nome.endswith(".csv"):
            df = pd.read_csv(arquivo)

        elif nome.endswith(".xlsx"):
            df = pd.read_excel(arquivo, engine="openpyxl")

        elif nome.endswith(".xls"):
            df = pd.read_excel(arquivo, engine="xlrd")

        elif nome.endswith(".ods"):
            df = pd.read_excel(arquivo, engine="odf")

        else:
            flash("Formato não suportado.")
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


# ==========================================================
# FORMULÁRIOS
# ==========================================================
@app.route("/formularios")
@login_required
def formularios():

    lista = supabase.table("formularios") \
        .select("*") \
        .order("created_at", desc=True) \
        .execute()

    return render_template(
        "formularios.html",
        formularios=lista.data
    )


@app.route("/novo-formulario", methods=["GET", "POST"])
@login_required
def novo_formulario():

    if request.method == "POST":

        token = str(int(time.time()))

        dados = {
            "tipo": request.form.get("tipo"),
            "titulo": request.form.get("titulo"),
            "descricao": request.form.get("descricao"),
            "token": token,
            "status": "ativo"
        }

        supabase.table("formularios").insert(dados).execute()

        return redirect(url_for("formularios"))

    return render_template("novo_formulario.html")


@app.route("/formulario/<id>/perguntas")
@login_required
def perguntas_formulario(id):

    form = supabase.table("formularios") \
        .select("*") \
        .eq("id", id) \
        .single() \
        .execute()

    perguntas = supabase.table("perguntas_formulario") \
        .select("*") \
        .eq("formulario_id", id) \
        .order("ordem") \
        .execute()

    return render_template(
        "perguntas.html",
        formulario=form.data,
        perguntas=perguntas.data
    )


@app.route("/pergunta/nova/<formulario_id>", methods=["POST"])
@login_required
def nova_pergunta(formulario_id):

    dados = {
        "formulario_id": formulario_id,
        "pergunta": request.form.get("pergunta"),
        "tipo": request.form.get("tipo"),
        "ordem": request.form.get("ordem"),
        "obrigatoria": True
    }

    supabase.table("perguntas_formulario").insert(dados).execute()

    return redirect(url_for(
        "perguntas_formulario",
        id=formulario_id
    ))


@app.route("/pergunta/editar/<id>", methods=["POST"])
@login_required
def editar_pergunta(id):

    dados = {
        "pergunta": request.form.get("pergunta"),
        "tipo": request.form.get("tipo"),
        "ordem": request.form.get("ordem")
    }

    supabase.table("perguntas_formulario") \
        .update(dados) \
        .eq("id", id) \
        .execute()

    return redirect(request.referrer)


@app.route("/pergunta/excluir/<id>")
@login_required
def excluir_pergunta(id):

    pergunta = supabase.table("perguntas_formulario") \
        .select("formulario_id") \
        .eq("id", id) \
        .single() \
        .execute()

    formulario_id = pergunta.data["formulario_id"]

    supabase.table("perguntas_formulario") \
        .delete() \
        .eq("id", id) \
        .execute()

    return redirect(url_for(
        "perguntas_formulario",
        id=formulario_id
    ))


# ==========================================================
# FORMULÁRIO PÚBLICO DINÂMICO
# ==========================================================
@app.route("/formulario/<token>")
def responder_formulario(token):

    form = supabase.table("formularios") \
        .select("*") \
        .eq("token", token) \
        .single() \
        .execute()

    perguntas = supabase.table("perguntas_formulario") \
        .select("*") \
        .eq("formulario_id", form.data["id"]) \
        .order("ordem") \
        .execute()

    return render_template(
        "responder_formulario.html",
        formulario=form.data,
        perguntas=perguntas.data
    )


@app.route("/responder-formulario", methods=["POST"])
def salvar_formulario():

    try:
        formulario_id = request.form.get("formulario_id")

        perguntas = supabase.table("perguntas_formulario") \
            .select("*") \
            .eq("formulario_id", formulario_id) \
            .execute()

        for p in perguntas.data:

            campo = f"pergunta_{p['id']}"
            resposta = request.form.get(campo)

            supabase.table("respostas_formulario").insert({
                "formulario_id": formulario_id,
                "pergunta_id": p["id"],
                "resposta": resposta
            }).execute()

        return render_template("obrigado.html")

    except Exception as e:
        return f"Erro ao salvar formulário: {str(e)}"


# ==========================================================
# RELATÓRIOS
# ==========================================================
@app.route("/relatorios")
@login_required
def relatorios():

    try:
        feedbacks = supabase.table("respostas")\
            .select("nota,comentario,created_at,treinamentos(titulo)")\
            .order("created_at", desc=True)\
            .limit(20)\
            .execute()

        lista = []

        for item in feedbacks.data:
            lista.append({
                "nota": item["nota"],
                "comentario": item["comentario"],
                "titulo": item["treinamentos"]["titulo"] if item["treinamentos"] else "Treinamento",
            })

        return render_template(
            "relatorios.html",
            feedbacks=lista
        )

    except Exception as e:
        return str(e)


# ==========================================================
# EXPORTAR PDF
# ==========================================================
@app.route("/exportar-pdf")
@login_required
def exportar_pdf():

    try:
        res = supabase.table("treinamentos") \
            .select("titulo, instrutor, setor") \
            .execute()

        treinamentos = res.data

        output = io.BytesIO()
        p = canvas.Canvas(output, pagesize=A4)

        width, height = A4

        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, height - 50, "Relatório de Treinamentos - NPS")

        y = height - 100
        p.setFont("Helvetica", 12)

        for t in treinamentos:

            texto = f"Curso: {t['titulo']} | Instrutor: {t['instrutor']} ({t['setor']})"
            p.drawString(100, y, texto)

            y -= 20

            if y < 50:
                p.showPage()
                y = height - 50

        p.save()
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="relatorio_nps.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        return f"Erro ao gerar PDF: {str(e)}"
@app.route("/exportar-excel")
@login_required
def exportar_excel():
    try:
        res = supabase.table("respostas")\
            .select("nota,comentario,clareza,aplicabilidade,instrutor,created_at")\
            .order("created_at", desc=True)\
            .execute()

        df = pd.DataFrame(res.data)

        output = io.BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Feedbacks")

        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="feedbacks.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
    return f"Erro ao gerar Excel: {str(e)}"

# ==========================================================
# PESQUISA ANTIGA (TREINAMENTO)
# ==========================================================
@app.route("/pesquisa")
def pesquisa():

    id_treino = request.args.get("id_treino")

    treino = supabase.table("treinamentos") \
        .select("titulo") \
        .eq("id", id_treino) \
        .single() \
        .execute()

    return render_template(
        "feedback_form.html",
        treinamento_id=id_treino,
        treinamento_nome=treino.data["titulo"]
    )


@app.route("/salvar-pesquisa", methods=["POST"])
def salvar_pesquisa():

    try:
        dados = {
            "treinamento_id": request.form.get("treinamento_id"),
            "nota": int(request.form.get("nota")),
            "comentario": request.form.get("comentario"),
            "clareza": int(request.form.get("clareza", 0)),
            "aplicabilidade": int(request.form.get("aplicabilidade", 0)),
            "instrutor": int(request.form.get("instrutor", 0))
        }

        supabase.table("respostas").insert(dados).execute()

        return render_template("obrigado.html")

    except Exception as e:
        return f"Erro ao salvar pesquisa: {str(e)}"


# ==========================================================
# START
# ==========================================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000))
    )