from flask import Flask, render_template, request, redirect, send_file
import sqlite3
from datetime import datetime
import requests
import pandas as pd
import plotly.express as px
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash



app = Flask(__name__)
app.secret_key = "segredo_super_secreto_123"
DB_PATH = "loja.db"
OPENCAGE_API_KEY = "c9aac9c2ac4b468fbd700c9dc1489763"

def criar_tabela():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pontos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            endereco TEXT
        )
    ''')
    con.commit()
    con.close()


def criar_tabela_funcionarios():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            sobrenome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            data_nascimento TEXT NOT NULL,
            senha_hash TEXT NOT NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS log_reset_senha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            funcionario_id INTEGER,
            nome_funcionario TEXT,
            data_hora TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            endereco TEXT,
            FOREIGN KEY (funcionario_id) REFERENCES funcionarios(id) ON DELETE SET NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS log_exclusao_funcionarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            sobrenome TEXT,
            telefone TEXT,
            data_nascimento TEXT,
            latitude REAL,
            longitude REAL,
            endereco TEXT,
            data_hora TEXT
        )
    ''')

    con.commit()
    con.close()


def criar_tabela_admin():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS config_admin (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            senha_hash TEXT NOT NULL
        )
    """)

    # Verifica se já existe um admin cadastrado
    cur.execute("SELECT COUNT(*) FROM config_admin")
    if cur.fetchone()[0] == 0:
        # Define senha padrão 'MC1234' (com hash)
        senha_default = "MC1234"
        hash_senha = generate_password_hash(senha_default)
        cur.execute("INSERT INTO config_admin (id, nome, senha_hash) VALUES (1, 'admin', ?)", (hash_senha,))
        print("✅ Admin padrão criado com senha: MC1234")

    con.commit()
    con.close()



def obter_endereco(latitude, longitude):
    try:
        url = f"https://api.opencagedata.com/geocode/v1/json?q={latitude}+{longitude}&key={OPENCAGE_API_KEY}&language=pt-BR"
        response = requests.get(url)
        if response.status_code == 200:
            dados = response.json()
            if dados["results"]:
                return dados["results"][0]["formatted"]
    except Exception as e:
        print("Erro ao obter endereço:", e)
    return "Endereço não encontrado"

# Atualiza a rota index() no app.py para validar com nome completo
@app.route("/", methods=["GET", "POST"])
def selecao_perfil():
    return render_template("selecao_perfil.html")


@app.route("/registrar", methods=["GET", "POST"])
def registrar_ponto():
    if session.get("perfil") != "funcionario":
        return redirect("/")

    mensagem = None
    latitude = longitude = endereco = None

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("SELECT nome, sobrenome FROM funcionarios ORDER BY nome ASC")
    funcionarios = [f"{n} {s}" for n, s in cur.fetchall()]
    con.close()

    if request.method == "POST":
        nome_completo = request.form.get("nome")
        senha = request.form.get("senha")
        tipo = request.form.get("tipo")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if nome_completo and " " in nome_completo:
            nome, sobrenome = nome_completo.split(" ", 1)
        else:
            nome, sobrenome = nome_completo, ""

        con = sqlite3.connect(DB_PATH)
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.cursor()
        cur.execute("SELECT senha_hash FROM funcionarios WHERE nome = ? AND sobrenome = ?", (nome, sobrenome))
        row = cur.fetchone()

        if row:
            senha_hash = row[0]
            if check_password_hash(senha_hash, senha):
                endereco = obter_endereco(latitude, longitude)
                cur.execute("""
                    INSERT INTO pontos (nome, tipo, data_hora, latitude, longitude, endereco)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (nome_completo, tipo, data_hora, latitude, longitude, endereco))
                con.commit()
                mensagem = f"Ponto registrado para {nome_completo} ({tipo}) às {data_hora}"
            else:
                mensagem = "❌ Senha incorreta. Tente novamente."
        else:
            mensagem = "❌ Funcionário não encontrado."
        con.close()

    return render_template("index.html", mensagem=mensagem, latitude=latitude, longitude=longitude, endereco=endereco, funcionarios=funcionarios)

@app.route("/registros")
def registros():
    if session.get("perfil") != "admin":
        return redirect("/")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("""
        SELECT nome, tipo, data_hora, latitude, longitude, endereco
        FROM pontos ORDER BY data_hora DESC
    """)
    dados = cur.fetchall()
    con.close()
    return render_template("registros.html", dados=dados)

def carregar_dados_para_grafico():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    df = pd.read_sql_query("SELECT * FROM pontos", con)
    con.close()
    df['data_hora'] = pd.to_datetime(df['data_hora'])
    df['data'] = df['data_hora'].dt.date
    return df


def grafico_interativo_plotly(df) -> str:
    if df.empty:
        print("⚠️ DataFrame vazio — sem dados para gerar gráfico.")
        return "<p>Nenhum dado disponível para gerar gráfico.</p>"

    fig = px.histogram(
        df,
        x="nome",
        color="tipo",
        title="Marcações por Colaborador e Tipo",
        labels={"nome": "Colaborador", "tipo": "Tipo de Marcação"},
        barmode="group",
        text_auto=True
    )
    fig.update_layout(
        xaxis_title="Colaborador",
        yaxis_title="Quantidade",
        bargap=0.2,
        plot_bgcolor='white',
        font=dict(size=14)
    )

    # ➕ Retorna o HTML como string (sem salvar arquivo)
    return fig.to_html(include_plotlyjs='cdn', full_html=False)

# Atualiza rotas que renderizam selects: graficos, reset_senha
from flask import render_template
import pandas as pd

@app.route("/graficos")
def graficos():
    if session.get("perfil") != "admin":
        return redirect("/")
    df = carregar_dados_para_grafico()
    df["nome"] = df["nome"].astype(str)

    nome_filtro = request.args.get("nome", "").strip()
    tipo_filtro = request.args.get("tipo", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()

    if nome_filtro:
        df = df[df["nome"].str.contains(nome_filtro, case=False, na=False)]
    if tipo_filtro:
        df = df[df["tipo"] == tipo_filtro]
    if data_inicio:
        try:
            df = df[df["data_hora"] >= pd.to_datetime(data_inicio)]
        except:
            pass
    if data_fim:
        try:
            df = df[df["data_hora"] <= pd.to_datetime(data_fim)]
        except:
            pass

    html_grafico = grafico_interativo_plotly(df)

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("SELECT nome, sobrenome FROM funcionarios ORDER BY nome ASC")
    funcionarios = [f"{n} {s}" for n, s in cur.fetchall()]
    con.close()

    return render_template("graficos.html", html_grafico=html_grafico, funcionarios=funcionarios)

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if session.get("perfil") != "admin":
        return redirect("/")
    mensagem = None

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        sobrenome = request.form.get("sobrenome", "").strip()
        telefone = request.form.get("telefone", "").strip()
        data_nascimento = request.form.get("data_nascimento", "").strip()
        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if not all([nome, sobrenome, telefone, data_nascimento, senha, confirmar_senha]):
            mensagem = "⚠️ Todos os campos são obrigatórios."
        elif senha != confirmar_senha:
            mensagem = "❌ As senhas não coincidem."
        else:
            senha_hash = generate_password_hash(senha)
            con = sqlite3.connect(DB_PATH)
            con.execute("PRAGMA foreign_keys = ON")
            cur = con.cursor()
            cur.execute("""
                INSERT INTO funcionarios (nome, sobrenome, telefone, data_nascimento, senha_hash)
                VALUES (?, ?, ?, ?, ?)
            """, (nome, sobrenome, telefone, data_nascimento, senha_hash))
            con.commit()
            con.close()
            mensagem = f"✅ Funcionário {nome} {sobrenome} cadastrado com sucesso!"

    return render_template("cadastro.html", mensagem=mensagem)

@app.route("/reset_senha", methods=["GET", "POST"])
def reset_senha():
    if session.get("perfil") not in ["admin", "funcionario"]:
        return redirect("/")

    mensagem = None
    nome = session.get("nome_funcionario") if session["perfil"] == "funcionario" else None

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ADMIN vê todos os nomes
    if session["perfil"] == "admin":
        cur.execute("SELECT nome, sobrenome FROM funcionarios ORDER BY nome ASC")
        funcionarios = [f"{n} {s}" for n, s in cur.fetchall()]
    else:
        funcionarios = [nome]

    if request.method == "POST":
        nome_selecionado = request.form.get("nome")
        data_nascimento = request.form.get("data_nascimento", "").strip()
        nova_senha = request.form.get("nova_senha")
        confirmar = request.form.get("confirmar_senha")

        if nova_senha != confirmar:
            mensagem = "❌ As senhas não coincidem."
        elif len(nova_senha) < 4:
            mensagem = "❌ A nova senha deve ter pelo menos 4 caracteres."
        else:
            nome_partes = nome_selecionado.split(" ", 1)
            nome, sobrenome = nome_partes if len(nome_partes) > 1 else (nome_partes[0], "")

            cur.execute("SELECT data_nascimento FROM funcionarios WHERE nome = ? AND sobrenome = ?", (nome, sobrenome))
            row = cur.fetchone()

            if session["perfil"] == "funcionario":
                if not row or row[0] != data_nascimento:
                    mensagem = "❌ Data de nascimento incorreta."
                    con.close()
                    return render_template("reset_senha.html", funcionarios=funcionarios, mensagem=mensagem)

            hash_nova = generate_password_hash(nova_senha)
            cur.execute("UPDATE funcionarios SET senha_hash = ? WHERE nome = ? AND sobrenome = ?", (hash_nova, nome, sobrenome))
            con.commit()
            mensagem = "✅ Senha redefinida com sucesso."
            con.close()
            return render_template("reset_senha.html", funcionarios=funcionarios, mensagem=mensagem)

    con.close()
    return render_template("reset_senha.html", funcionarios=funcionarios, mensagem=mensagem)

@app.route("/funcionarios", methods=["GET"])
def funcionarios():
    if session.get("perfil") != "admin":
        return redirect("/")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("SELECT id, nome, sobrenome, telefone, data_nascimento FROM funcionarios ORDER BY nome ASC")
    funcionarios = cur.fetchall()
    con.close()
    return render_template("funcionarios.html", funcionarios=funcionarios)

# Nova rota: exclusão de funcionário por ID
@app.route("/excluir_funcionario", methods=["POST"])
def excluir_funcionario():
    if session.get("perfil") != "admin":
        return redirect("/")
    funcionario_id = request.form.get("funcionario_id")
    latitude = request.form.get("latitude", "")
    longitude = request.form.get("longitude", "")
    endereco = obter_endereco(latitude, longitude)

    if funcionario_id:
        con = sqlite3.connect(DB_PATH)
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.cursor()

        # 🔍 Busca os dados completos antes de excluir
        cur.execute("SELECT nome, sobrenome, telefone, data_nascimento FROM funcionarios WHERE id = ?", (funcionario_id,))
        row = cur.fetchone()

        if row:
            nome, sobrenome, telefone, data_nascimento = row
            data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 📝 Registro completo no log
            cur.execute("""
                INSERT INTO log_exclusao_funcionarios 
                (nome, sobrenome, telefone, data_nascimento, data_hora, latitude, longitude, endereco)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (nome, sobrenome, telefone, data_nascimento, data_hora, latitude, longitude, endereco))

            # ❌ Exclui da tabela original
            cur.execute("DELETE FROM funcionarios WHERE id = ?", (funcionario_id,))

        con.commit()
        con.close()

    return redirect("/funcionarios")


@app.route("/exportar_funcionarios")
def exportar_funcionarios():
    if session.get("perfil") != "admin":
        return redirect("/")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("SELECT nome, sobrenome, telefone, data_nascimento FROM funcionarios")
    dados = cur.fetchall()
    con.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Nome", "Sobrenome", "Telefone", "Data de Nascimento"])
    writer.writerows(dados)
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode('utf-8')), mimetype="text/csv", as_attachment=True, download_name="funcionarios.csv")

@app.route("/exportar_grafico_csv")
def exportar_grafico_csv():
    if session.get("perfil") != "admin":
        return redirect("/")
    df = carregar_dados_para_grafico()
    nome_filtro = request.args.get("nome", "").strip()
    tipo_filtro = request.args.get("tipo", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim = request.args.get("data_fim", "").strip()

    if nome_filtro:
        df = df[df["nome"].str.contains(nome_filtro, case=False, na=False)]
    if tipo_filtro:
        df = df[df["tipo"] == tipo_filtro]
    if data_inicio:
        try:
            df = df[df["data_hora"] >= pd.to_datetime(data_inicio)]
        except:
            pass
    if data_fim:
        try:
            df = df[df["data_hora"] <= pd.to_datetime(data_fim)]
        except:
            pass

    output = io.StringIO()
    df.to_csv(output, index=False, columns=["nome", "tipo", "data_hora", "latitude", "longitude", "endereco"])
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode('utf-8')), mimetype="text/csv", as_attachment=True, download_name="grafico_marcacoes.csv")

@app.route("/exportar_registros_csv")
def exportar_registros_csv():
    if session.get("perfil") != "admin":
        return redirect("/")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    df = pd.read_sql_query("SELECT nome, tipo, data_hora, latitude, longitude, endereco FROM pontos ORDER BY data_hora DESC", con)
    con.close()

    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode('utf-8')), mimetype="text/csv", as_attachment=True, download_name="registros.csv")


from flask import session, redirect, url_for, render_template, request, flash

@app.route("/login_admin", methods=["GET", "POST"])
def login_admin():
    if request.method == "POST":
        senha = request.form.get("senha", "").strip()

        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT senha_hash FROM config_admin WHERE id = 1")
        row = cur.fetchone()
        con.close()

        senha_valida = False

        if row:
            senha_hash = row[0]
            senha_valida = check_password_hash(senha_hash, senha)

        # Caso senha válida OU senha padrão 'MC1234'
        if senha_valida or senha == "MC1234":
            session["perfil"] = "admin"
            flash("Login de administrador realizado com sucesso.", "success")
            return redirect("/funcionarios")  # Página inicial para admins
        else:
            flash("Senha incorreta. Tente novamente.", "danger")
            return render_template("login_admin.html")

    return render_template("login_admin.html")


@app.route("/login_funcionario", methods=["GET", "POST"])
def login_funcionario():
    mensagem = None
    funcionarios = []

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT nome, sobrenome FROM funcionarios ORDER BY nome ASC")
    funcionarios = [f"{n} {s}" for n, s in cur.fetchall()]
    con.close()

    if request.method == "POST":
        nome_completo = request.form.get("nome", "").strip()
        senha = request.form.get("senha", "").strip()

        if nome_completo and " " in nome_completo:
            nome, sobrenome = nome_completo.split(" ", 1)
        else:
            nome, sobrenome = nome_completo, ""

        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT senha_hash FROM funcionarios WHERE nome = ? AND sobrenome = ?", (nome, sobrenome))
        row = cur.fetchone()
        con.close()

        if row and check_password_hash(row[0], senha):
            session["perfil"] = "funcionario"
            session["nome_funcionario"] = nome_completo
            return redirect("/registrar")
        else:
            mensagem = "❌ Nome ou senha inválidos."

    return render_template("login_funcionario.html", mensagem=mensagem, funcionarios=funcionarios)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/config_admin", methods=["GET", "POST"])
def config_admin():
    if session.get("perfil") != "admin":
        return redirect("/")

    mensagem = None

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "").strip()
        nova_senha = request.form.get("nova_senha", "").strip()
        confirmar = request.form.get("confirmar_senha", "").strip()

        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT senha_hash FROM config_admin WHERE id = 1")
        row = cur.fetchone()

        senha_hash = row[0] if row else ""
        senha_correta = check_password_hash(senha_hash, senha_atual) or senha_atual == "MC1234"

        if not senha_correta:
            mensagem = "❌ Senha atual incorreta."
        elif nova_senha != confirmar:
            mensagem = "❌ A nova senha e a confirmação não coincidem."
        elif len(nova_senha) < 4:
            mensagem = "❌ A nova senha deve ter pelo menos 4 caracteres."
        else:
            novo_hash = generate_password_hash(nova_senha)
            cur.execute("UPDATE config_admin SET senha_hash = ? WHERE id = 1", (novo_hash,))
            con.commit()
            mensagem = "✅ Senha alterada com sucesso."
        con.close()

    return render_template("config_admin.html", mensagem=mensagem)

@app.route("/logs")
def logs():
    if session.get("perfil") != "admin":
        return redirect("/")
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ✅ Log de redefinição de senha (já com nome completo)
    cur.execute("""
        SELECT nome_funcionario, data_hora, latitude, longitude, endereco
        FROM log_reset_senha
        ORDER BY data_hora DESC
    """)
    reset_logs = cur.fetchall()

    # ✅ Log de exclusão (dados armazenados diretamente)
    cur.execute("""
        SELECT nome, sobrenome, telefone, data_nascimento, data_hora, latitude, longitude, endereco
        FROM log_exclusao_funcionarios
        ORDER BY data_hora DESC
    """)
    exclusao_logs = cur.fetchall()

    con.close()
    return render_template("logs.html", reset_logs=reset_logs, exclusao_logs=exclusao_logs)

import webbrowser
from threading import Timer

def abrir_navegador():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    from werkzeug.serving import is_running_from_reloader

    criar_tabela()
    criar_tabela_funcionarios()
    criar_tabela_admin()  # ✅ Adicionado

    if not is_running_from_reloader():
        Timer(1, abrir_navegador).start()

    app.run(debug=True)