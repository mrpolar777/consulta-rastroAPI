import streamlit as st
import requests
import datetime
import math
import pandas as pd
import io

# Função Haversine
def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

st.title("Relatório de Veículos - Rastro System")

# Sidebar
st.sidebar.header("Credenciais API")
username = st.sidebar.text_input("Login")
password = st.sidebar.text_input("Senha", type="password")
user_id = st.sidebar.text_input("ID do Usuário (opcional)", value="")
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
            usuario_id = user_id.strip() or str(login_json.get("id"))
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
                    date_str = date_input.strftime("%d/%m/%Y")

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    total = len(dispositivos)
                    for idx, dispositivo in enumerate(dispositivos):
                        vehicle_name = dispositivo.get("name", "Sem Nome")
                        status_text.text(f"Processando: {vehicle_name} ({idx + 1}/{total})")

                        vehicle_id = dispositivo.get("veiculo_id")
                        historico_url = "http://teresinagps.rastrosystem.com.br/api_v2/veiculo/historico/"
                        historico_data = {
                            "data": date_str,
                            "hora_ini": hora_ini,
                            "hora_fim": hora_fim,
                            "veiculo": vehicle_id
                        }

                        historico_resp = requests.post(historico_url, headers=headers, json=historico_data)
                        registros = historico_resp.json().get("veiculos", [])

                        total_distance = 0
                        tempo_ignicao_ligada = datetime.timedelta()
                        velocidades = []
                        velocidade_maxima = 0

                        if registros:
                            for item in registros:
                                item["dt"] = datetime.datetime.strptime(item["server_time"], "%d/%m/%Y %H:%M:%S")
                            registros.sort(key=lambda x: x["dt"])

                            tempo_inicio_ignicao = None
                            for i in range(1, len(registros)):
                                prev, curr = registros[i - 1], registros[i]

                                lat1, lon1 = float(prev["latitude"]), float(prev["longitude"])
                                lat2, lon2 = float(curr["latitude"]), float(curr["longitude"])

                                if prev["ignicao"] == '1':
                                    total_distance += haversine(lon1, lat1, lon2, lat2)

                                if curr["ignicao"] == '1':
                                    vel = float(curr.get("velocidade", 0))
                                    velocidades.append(vel)
                                    velocidade_maxima = max(velocidade_maxima, vel)

                                if prev["ignicao"] == '0' and curr["ignicao"] == '1':
                                    tempo_inicio_ignicao = curr["dt"]
                                elif prev["ignicao"] == '1' and curr["ignicao"] == '0' and tempo_inicio_ignicao:
                                    tempo_ignicao_ligada += curr["dt"] - tempo_inicio_ignicao
                                    tempo_inicio_ignicao = None

                            if tempo_inicio_ignicao:
                                tempo_ignicao_ligada += registros[-1]["dt"] - tempo_inicio_ignicao

                        velocidade_media = round(sum(velocidades) / len(velocidades), 1) if velocidades else 0
                        consumo_litros = total_distance / km_por_litro
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
                    st.dataframe(df)

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    output.seek(0)

                    st.download_button(
                        "Baixar Excel", output, "relatorio_veiculos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
