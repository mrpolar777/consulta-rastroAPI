import streamlit as st
import requests
import datetime
import math
import pandas as pd
import io

# Função para calcular distância entre dois pontos geográficos
def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Carrega a planilha com nomes corretos dos veículos
relacao_path = "Relação Rotas e Rastreador.xlsx"
relacao_df = pd.read_excel(relacao_path)
placa_para_nome = relacao_df.dropna(subset=["Placa"]).drop_duplicates("Placa").set_index("Placa")["Veículo"].to_dict()

# Interface do Streamlit
st.title("Relatório de Veículos - Rastro System")

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
            usuario_id = user_id if user_id.strip() != "" else str(login_json.get("id"))
            st.info(f"ID do usuário: {usuario_id}")
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
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    total = len(dispositivos)

                    for idx, dispositivo in enumerate(dispositivos):
                        placa = dispositivo.get("placa", "Não informada")
                        # Substitui o nome do veículo baseado na placa, priorizando a planilha
                        vehicle_name = placa_para_nome.get(placa, f"{dispositivo.get('name', 'Sem Nome')} (sem correspondência)")
                        vehicle_id = dispositivo.get("veiculo_id")
                        status_text.text(f"Processando: {vehicle_name} ({idx + 1}/{total})")

                        historico_url = "http://teresinagps.rastrosystem.com.br/api_v2/veiculo/historico/"
                        historico_data = {
                            "data": date_input.strftime("%d/%m/%Y"),
                            "hora_ini": hora_ini,
                            "hora_fim": hora_fim,
                            "veiculo": vehicle_id
                        }

                        total_distance = 0
                        velocidades = []
                        velocidade_maxima = 0

                        historico_resp = requests.post(historico_url, headers=headers, json=historico_data)
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

                        velocidade_media = round(sum(velocidades) / len(velocidades), 1) if velocidades else 0

                        if velocidade_media > 0:
                            tempo_horas = total_distance / velocidade_media
                            tempo_segundos = int(tempo_horas * 3600)
                            tempo_estimado = datetime.timedelta(seconds=tempo_segundos)
                        else:
                            tempo_estimado = datetime.timedelta()

                        consumo_litros = total_distance / km_por_litro if km_por_litro > 0 else 0
                        custo = consumo_litros * preco_combustivel

                        resultados.append({
                            "Veículo": vehicle_name,
                            "Placa": placa,
                            "Distância (km)": round(total_distance, 2),
                            "Tempo": str(tempo_estimado),
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
                        "Placa",
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
