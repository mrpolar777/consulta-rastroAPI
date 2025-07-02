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

def horas_para_tempo_formatado(horas_float):
    total_segundos = int(horas_float * 3600)
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    segundos = total_segundos % 60
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

tipos_veiculo = {
    "1": "Automóvel",
    "3": "Van",
    "7": "Ônibus",
    "12": "Micro-ônibus"
}

def identificar_tipo_frota(nome):
    nome_lower = nome.lower()
    if "própria" in nome_lower:
        return "Própria"
    elif "terceir" in nome_lower or "locadora" in nome_lower:
        return "Terceira"
    elif "subloc" in nome_lower or "sub" in nome_lower:
        return "Sublocada"
    else:
        return "Não Informada"

st.title("Relatório de Veículos - Rastro System")

# Sidebar
st.sidebar.header("Credenciais API")
username = st.sidebar.text_input("Login")
password = st.sidebar.text_input("Senha", type="password")
user_id = st.sidebar.text_input("ID do Usuário (opcional)", value="")
app_number = 4

st.sidebar.header("Configurações do Relatório")
start_date = st.sidebar.date_input("Data Inicial", datetime.date.today())
end_date = st.sidebar.date_input("Data Final", datetime.date.today())
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

            veiculos_url = f"http://teresinagps.rastrosystem.com.br/api_v2/veiculos/{usuario_id}/"
            headers = {"Authorization": f"token {token}"}
            veiculos_resp = requests.get(veiculos_url, headers=headers)

            if veiculos_resp.status_code != 200:
                st.error("Erro ao obter veículos.")
            else:
                dispositivos = veiculos_resp.json().get("dispositivos", [])
                if not dispositivos:
                    st.error("Nenhum veículo encontrado.")
                    st.stop()

                resultados = []
                erros_processamento = []
                logs_internos = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                total = len(dispositivos)

                for idx, dispositivo in enumerate(dispositivos):
                    try:
                        vehicle_name = dispositivo.get("name", "Sem Nome")
                        placa = dispositivo.get("placa", "Não informada")
                        vehicle_id = dispositivo.get("veiculo_id")
                        tipo_codigo = str(dispositivo.get("tipo", ""))
                        tipo_veiculo = tipos_veiculo.get(tipo_codigo, "Desconhecido")
                        tipo_frota = identificar_tipo_frota(vehicle_name)

                        status_text.text(f"Processando: {vehicle_name} ({idx + 1}/{total})")

                        total_distance = 0
                        velocidades = []
                        velocidade_maxima = 0
                        current_date = start_date
                        registros_totais = 0

                        while current_date <= end_date:
                            historico_url = "http://teresinagps.rastrosystem.com.br/api_v2/veiculo/historico/"
                            historico_data = {
                                "data": current_date.strftime("%d/%m/%Y"),
                                "hora_ini": hora_ini,
                                "hora_fim": hora_fim,
                                "veiculo": vehicle_id
                            }
                            historico_resp = requests.post(historico_url, headers=headers, json=historico_data)

                            if historico_resp.status_code == 200:
                                registros = historico_resp.json().get("veiculos", [])
                                registros_totais += len(registros)

                                try:
                                    for item in registros:
                                        item["dt"] = datetime.datetime.strptime(item["server_time"], "%d/%m/%Y %H:%M:%S")
                                    registros = sorted(registros, key=lambda x: x["dt"])
                                except Exception as e:
                                    logs_internos.append(f"{vehicle_name}: erro ao processar datas - {e}")
                                    registros = []

                                for i in range(1, len(registros)):
                                    try:
                                        lat1, lon1 = float(registros[i - 1]["latitude"]), float(registros[i - 1]["longitude"])
                                        lat2, lon2 = float(registros[i]["latitude"]), float(registros[i]["longitude"])
                                        total_distance += haversine(lon1, lat1, lon2, lat2)

                                        vel = float(registros[i].get("velocidade", 0))
                                        velocidades.append(vel)
                                        velocidade_maxima = max(velocidade_maxima, vel)
                                    except:
                                        logs_internos.append(f"{vehicle_name}: coordenadas inválidas em {current_date.strftime('%d/%m/%Y')}")
                            else:
                                logs_internos.append(f"{vehicle_name}: erro histórico em {current_date.strftime('%d/%m/%Y')}")

                            current_date += datetime.timedelta(days=1)

                        velocidade_media = round(sum(velocidades) / len(velocidades), 1) if velocidades else 0
                        tempo_em_horas = round(total_distance / velocidade_media, 2) if velocidade_media > 0 else 0

                        consumo_litros = total_distance / km_por_litro if km_por_litro > 0 else 0
                        custo = consumo_litros * preco_combustivel

                        resultados.append({
                            "Veículo": vehicle_name,
                            "Placa": placa,
                            "Tipo de Veículo": tipo_veiculo,
                            "Tipo de Frota": tipo_frota,
                            "Distância (km)": round(total_distance, 2),
                            "Tempo (h)": round(tempo_em_horas, 2),
                            "Tempo formatado": horas_para_tempo_formatado(tempo_em_horas),
                            "Velocidade Média (km/h)": velocidade_media,
                            "Velocidade Máxima (km/h)": velocidade_maxima,
                            "Km/L": km_por_litro,
                            "Consumo (L)": round(consumo_litros, 2),
                            "Custo (R$)": round(custo, 2)
                        })

                    except Exception as e:
                        erros_processamento.append(f"{dispositivo.get('name', 'Sem nome')} - {str(e)}")

                    progress_bar.progress((idx + 1) / total)

                status_text.text("✅ Relatório finalizado.")

                if not resultados:
                    st.error("Nenhum dado processado com sucesso.")
                    st.stop()

                df = pd.DataFrame(resultados)
                colunas_ordenadas = [
                    "Veículo", "Placa", "Tipo de Veículo", "Tipo de Frota",
                    "Distância (km)", "Tempo (HH:MM:SS)", "Velocidade Média (km/h)",
                    "Velocidade Máxima (km/h)", "Km/L", "Consumo (L)", "Custo (R$)"
                ]
                df = df[colunas_ordenadas]

                st.success("✅ Relatório gerado com sucesso!")
                st.dataframe(df)

                try:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False, sheet_name='Relatório')
                    output.seek(0)
                    st.download_button(
                        label="📥 Baixar Excel",
                        data=output,
                        file_name="relatorio_veiculos.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar o Excel: {e}")
