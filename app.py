import streamlit as st
import requests
import datetime
import math
import pandas as pd
import io

def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

st.title("Relatório de Veículos - Rastro System")

# Sidebar
st.sidebar.header("Credenciais API")
username = st.sidebar.text_input("Login")
password = st.sidebar.text_input("Senha", type="password")
user_id = st.sidebar.text_input("ID do Usuário (obrigatório)", value="")
app_number = 4

st.sidebar.header("Configurações do Relatório")
date_input = st.sidebar.date_input("Data", datetime.date.today())
hora_ini = st.sidebar.text_input("Hora Início", "00:00:00")
hora_fim = st.sidebar.text_input("Hora Fim", "23:59:59")
km_por_litro = st.sidebar.number_input("Km/L", min_value=0.1, value=3.0, step=0.1)
preco_combustivel = st.sidebar.number_input("Preço do Litro (R$)", min_value=0.1, value=7.0, step=0.1)

if st.sidebar.button("Gerar Relatório"):
    login_url = "http://teresinagps.rastrosystem.com.br/api_v2/login/"
    login_data = {"login": username, "senha": password, "app": app_number}
    with st.spinner("Fazendo login..."):
        login_response = requests.post(login_url, data=login_data)

    if login_response.status_code != 200:
        st.error("Erro no login.")
    else:
        login_json = login_response.json()
        token = login_json.get("token")
        if not token:
            st.error("Token não retornado.")
        else:
            usuario_id = user_id.strip()
            if not usuario_id:
                st.error("ID do Usuário é obrigatório para buscar notificações.")
                st.stop()

            veiculos_url = f"http://teresinagps.rastrosystem.com.br/api_v2/veiculos/{usuario_id}/"
            headers = {"Authorization": f"token {token}"}
            veiculos_resp = requests.get(veiculos_url, headers=headers)

            if veiculos_resp.status_code != 200:
                st.error("Erro ao obter veículos.")
            else:
                dispositivos = veiculos_resp.json().get("dispositivos", [])
                if not dispositivos:
                    st.warning("Nenhum veículo encontrado.")
                else:
                    resultados = []
                    data_consulta = date_input.strftime("%Y-%m-%d")
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    total = len(dispositivos)
                    for idx, dispositivo in enumerate(dispositivos):
                        vehicle_name = dispositivo.get("name", "Sem Nome")
                        placa = dispositivo.get("placa", "")
                        vehicle_id = dispositivo.get("veiculo_id")
                        status_text.text(f"Processando: {vehicle_name} ({idx + 1}/{total})")

                        # 1. BUSCAR HISTÓRICO PARA DISTÂNCIA
                        historico_url = "http://teresinagps.rastrosystem.com.br/api_v2/veiculo/historico/"
                        historico_data = {
                            "data": date_input.strftime("%d/%m/%Y"),
                            "hora_ini": hora_ini,
                            "hora_fim": hora_fim,
                            "veiculo": vehicle_id
                        }
                        historico_resp = requests.post(historico_url, headers=headers, json=historico_data)

                        total_distance = 0
                        velocidades = []
                        velocidade_maxima = 0

                        if historico_resp.status_code == 200:
                            registros = historico_resp.json().get("veiculos", [])
                            try:
                                for item in registros:
                                    item["dt"] = datetime.datetime.strptime(item["server_time"], "%d/%m/%Y %H:%M:%S")
                                registros = sorted(registros, key=lambda x: x["dt"])
                            except:
                                registros = []

                            for i in range(1, len(registros)):
                                prev = registros[i - 1]
                                curr = registros[i]
                                lat1, lon1 = float(prev["latitude"]), float(prev["longitude"])
                                lat2, lon2 = float(curr["latitude"]), float(curr["longitude"])
                                total_distance += haversine(lon1, lat1, lon2, lat2)

                                vel = float(curr.get("velocidade", 0))
                                velocidades.append(vel)
                                velocidade_maxima = max(velocidade_maxima, vel)

                        # 2. BUSCAR NOTIFICAÇÕES PARA TEMPO LIGADO
                        notificacoes_url = f"http://teresinagps.rastrosystem.com.br/api_v2/get-user-notifications/{usuario_id}"
                        notificacoes_resp = requests.get(notificacoes_url, headers=headers)

                        tempo_ignicao_ligada = datetime.timedelta()
                        if notificacoes_resp.status_code == 200:
                            eventos = notificacoes_resp.json()
                            eventos_placa = [e for e in eventos if placa in e.get("title", "") and "ignição" in e.get("title", "").lower()]
                            eventos_placa.sort(key=lambda x: x["criado"])

                            acc_on = None
                            for ev in eventos_placa:
                                msg = ev.get("message", "").lower()
                                data = ev.get("criado")
                                try:
                                    dt = datetime.datetime.fromisoformat(data.replace("Z", "+00:00"))
                                except:
                                    continue

                                if dt.date() != date_input:
                                    continue

                                if "ligada" in msg:
                                    acc_on = dt
                                elif "desligada" in msg and acc_on:
                                    tempo_ignicao_ligada += dt - acc_on
                                    acc_on = None

                        velocidade_media = round(sum(velocidades) / len(velocidades), 1) if velocidades else 0
                        consumo_litros = total_distance / km_por_litro if km_por_litro > 0 else 0
                        custo = consumo_litros * preco_combustivel

                        resultados.append({
                            "Veículo": vehicle_name,
                            "Distância (km)": round(total_distance, 2),
                            "Tempo": str(tempo_ignicao_ligada),
                            "Velocidade Média (km/h)": velocidade_media,
                            "Velocidade Máxima (km/h)": velocidade_maxima,
                            "Km/L": km_por_litro,
                            "Consumo (L)": round(consumo_litros, 2),
                            "Custo (R$)": round(custo, 2)
                        })

                        progress_bar.progress((idx + 1) / total)

                    status_text.text("Relatório finalizado com sucesso!")

                    df = pd.DataFrame(resultados)
                    colunas_ordenadas = [
                        "Veículo",
                        "Distância (km)",
                        "Tempo",
                        "Velocidade Média (km/h)",
                        "Velocidade Máxima (km/h)",
                        "Km/L",
                        "Consumo (L)",
                        "Custo (R$)"
                    ]
                    df = df[colunas_ordenadas]

                    st.write("Relatório Gerado com Sucesso", df)

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Relatório')
                    output.seek(0)
                    xlsx_data = output.getvalue()

                    st.download_button(
                        label="Baixar Excel",
                        data=xlsx_data,
                        file_name="relatorio_veiculos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
