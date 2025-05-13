from flask import Flask, render_template, request, redirect, send_file
import sqlite3
from datetime import datetime
import requests
import pandas as pd
import plotly.express as px
from werkzeug.security import generate_password_hash, check_password_hash
import csv
import io

app = Flask(__name__)
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
def index():
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

def grafico_interativo_plotly(df):
    if df.empty:
        print("⚠️ DataFrame vazio — sem dados para gerar gráfico.")
        return None

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

    caminho_html = "static/grafico_interativo.html"
    fig.write_html(caminho_html, full_html=False)
    return caminho_html

# Atualiza rotas que renderizam selects: graficos, reset_senha
@app.route("/graficos")
def graficos():
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

    caminho_html = grafico_interativo_plotly(df)

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("SELECT nome, sobrenome FROM funcionarios ORDER BY nome ASC")
    funcionarios = [f"{n} {s}" for n, s in cur.fetchall()]  # ✅ Aqui a concatenação correta
    con.close()

    return render_template("graficos.html", html_grafico=caminho_html, funcionarios=funcionarios)

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
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
    mensagem = None
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    cur = con.cursor()
    cur.execute("SELECT nome, sobrenome FROM funcionarios ORDER BY nome ASC")
    funcionarios = [f"{n} {s}" for n, s in cur.fetchall()]  # ✅ Concatenação correta
    con.close()

    if request.method == "POST":
        nome_completo = request.form.get("nome", "").strip()
        data_nascimento = request.form.get("data_nascimento", "").strip()
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")
        latitude = request.form.get("latitude", "")
        longitude = request.form.get("longitude", "")

        if not all([nome_completo, data_nascimento, nova_senha, confirmar_senha]):
            mensagem = "⚠️ Todos os campos são obrigatórios."
        elif nova_senha != confirmar_senha:
            mensagem = "❌ As senhas não coincidem."
        else:
            if nome_completo and " " in nome_completo:
                nome, sobrenome = nome_completo.split(" ", 1)
            else:
                nome, sobrenome = nome_completo, ""

            con = sqlite3.connect(DB_PATH)
            con.execute("PRAGMA foreign_keys = ON")
            cur = con.cursor()
            cur.execute("""
                SELECT id FROM funcionarios
                WHERE nome = ? AND sobrenome = ? AND data_nascimento = ?
            """, (nome, sobrenome, data_nascimento))
            row = cur.fetchone()

            if row:
                funcionario_id = row[0]
                endereco = obter_endereco(latitude, longitude)
                senha_hash = generate_password_hash(nova_senha)
                cur.execute("UPDATE funcionarios SET senha_hash = ? WHERE id = ?", (senha_hash, funcionario_id))
                cur.execute("""
                    INSERT INTO log_reset_senha (funcionario_id, nome_funcionario, data_hora, latitude, longitude, endereco)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (funcionario_id, nome_completo, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), latitude, longitude, endereco))
                con.commit()
                mensagem = "✅ Senha redefinida com sucesso!"
            else:
                mensagem = "❌ Dados inválidos. Verifique o nome, sobrenome e a data de nascimento."
            con.close()

    return render_template("reset_senha.html", mensagem=mensagem, funcionarios=funcionarios)

@app.route("/funcionarios", methods=["GET"])
def funcionarios():
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
    funcionario_id = request.form.get("funcionario_id")
    latitude = request.form.get("latitude", "")
    longitude = request.form.get("longitude", "")
    endereco = obter_endereco(latitude, longitude)

    if funcionario_id:
        con = sqlite3.connect(DB_PATH)
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.cursor()

        # 🔍 Busca os dados do funcionário antes de excluir
        cur.execute("SELECT nome, sobrenome FROM funcionarios WHERE id = ?", (funcionario_id,))
        row = cur.fetchone()

        if row:
            nome, sobrenome = row
            data_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 📝 Registra no log de exclusão
            cur.execute("""
                INSERT INTO log_exclusao_funcionarios (nome, sobrenome, data_hora, latitude, longitude, endereco)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nome, sobrenome, data_hora, latitude, longitude, endereco))

            # ❌ Exclui da tabela original
            cur.execute("DELETE FROM funcionarios WHERE id = ?", (funcionario_id,))

        con.commit()
        con.close()

    return redirect("/funcionarios")


@app.route("/exportar_funcionarios")
def exportar_funcionarios():
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
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    df = pd.read_sql_query("SELECT nome, tipo, data_hora, latitude, longitude, endereco FROM pontos ORDER BY data_hora DESC", con)
    con.close()

    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode('utf-8')), mimetype="text/csv", as_attachment=True, download_name="registros.csv")


@app.route("/logs")
def logs():
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


if __name__ == "__main__":
    criar_tabela()
    criar_tabela_funcionarios()
    app.run(debug=True)