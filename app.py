import streamlit as st
import requests
import datetime
import math
import pandas as pd

# Função para cálculo da distância entre dois pontos usando a fórmula de Haversine (em km)
def haversine(lon1, lat1, lon2, lat2):
    R = 6371  # Raio da Terra em km
    dlon = math.radians(lon2 - lon1)
    dlat = math.radians(lat2 - lat1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance

st.title("Relatório de Veículos - Rastro System")

# Sidebar para entrada de credenciais e configurações do relatório
st.sidebar.header("Credenciais API")
username = st.sidebar.text_input("Login")
password = st.sidebar.text_input("Senha", type="password")
user_id = st.sidebar.text_input("ID do Usuário (opcional)", value="")  # caso não informado, usamos o id retornado no login
app_number = 4  # valor fixo conforme documentação

st.sidebar.header("Configurações do Relatório")
date_input = st.sidebar.date_input("Data", datetime.date.today())
hora_ini = st.sidebar.text_input("Hora Início (HH:MM:SS)", "00:00:00")
hora_fim = st.sidebar.text_input("Hora Fim (HH:MM:SS)", "23:59:59")
km_por_litro = st.sidebar.number_input("Km/L (Eficiência)", min_value=0.1, value=10.0, step=0.1)
preco_combustivel = st.sidebar.number_input("Preço do Combustível (R$/L)", min_value=0.1, value=5.0, step=0.1)

if st.sidebar.button("Gerar Relatório"):
    # Etapa 1: Realiza o login para obter o token
    login_url = "http://teresinagps.rastrosystem.com.br/api_v2/login/"
    login_data = {
        "login": username,
        "senha": password,
        "app": app_number
    }
    with st.spinner("Fazendo login..."):
        login_response = requests.post(login_url, data=login_data)
    if login_response.status_code != 200:
        st.error("Erro no login! Verifique suas credenciais.")
    else:
        login_json = login_response.json()
        token = login_json.get("token")
        if not token:
            st.error("Token não retornado. Verifique suas credenciais.")
        else:
            st.success("Login realizado com sucesso!")
            # Utiliza o ID do usuário retornado se não for informado manualmente
            usuario_id = user_id if user_id.strip() != "" else str(login_json.get("id"))
            
            # Etapa 2: Obter lista de veículos
            st.info("Obtendo lista de veículos...")
            veiculos_url = f"http://teresinagps.rastrosystem.com.br/api_v2/veiculos/{usuario_id}/"
            headers = {"Authorization": f"token {token}"}
            veiculos_resp = requests.get(veiculos_url, headers=headers)
            if veiculos_resp.status_code != 200:
                st.error("Erro ao obter a lista de veículos!")
            else:
                veiculos_data = veiculos_resp.json()
                dispositivos = veiculos_data.get("dispositivos", [])
                if not dispositivos:
                    st.warning("Nenhum veículo encontrado para este usuário.")
                else:
                    st.success(f"{len(dispositivos)} veículo(s) encontrado(s)!")
                    resultados = []
                    
                    # Conversão da data para o formato dd/mm/YYYY
                    date_str = date_input.strftime("%d/%m/%Y")
                    
                    # Para cada veículo, consulta o histórico e realiza os cálculos
                    for dispositivo in dispositivos:
                        vehicle_name = dispositivo.get("name", "Sem Nome")
                        vehicle_id = dispositivo.get("veiculo_id")
                        
                        historico_url = "http://teresinagps.rastrosystem.com.br/api_v2/veiculo/historico/"
                        historico_data = {
                            "data": date_str,
                            "hora_ini": hora_ini,
                            "hora_fim": hora_fim,
                            "veiculo": vehicle_id
                        }
                        historico_resp = requests.post(historico_url, headers=headers, json=historico_data)
                        if historico_resp.status_code != 200:
                            st.warning(f"Erro ao obter histórico para {vehicle_name}")
                            continue
                        
                        historico_json = historico_resp.json()
                        registros = historico_json.get("veiculos", [])
                        
                        # Se não houver dados de histórico, consideramos sem movimento
                        if not registros:
                            resultados.append({
                                "Veículo": vehicle_name,
                                "Distância (km)": 0,
                                "Tempo": "00:00:00",
                                "Km/L": km_por_litro,
                                "Consumo (L)": 0,
                                "Custo (R$)": 0
                            })
                        else:
                            # Processa os registros: converte "server_time" para datetime e ordena
                            try:
                                for item in registros:
                                    item["dt"] = datetime.datetime.strptime(item["server_time"], "%d/%m/%Y %H:%M:%S")
                                registros = sorted(registros, key=lambda x: x["dt"])
                            except Exception as e:
                                st.error(f"Erro ao processar datas do histórico para {vehicle_name}: {e}")
                                continue
                            
                            # Cálculo da distância total (soma das distâncias entre pontos consecutivos)
                            total_distance = 0
                            for i in range(1, len(registros)):
                                prev = registros[i - 1]
                                curr = registros[i]
                                lat1 = float(prev.get("latitude", 0))
                                lon1 = float(prev.get("longitude", 0))
                                lat2 = float(curr.get("latitude", 0))
                                lon2 = float(curr.get("longitude", 0))
                                total_distance += haversine(lon1, lat1, lon2, lat2)
                            
                            # Cálculo do tempo total (diferença entre o primeiro e o último registro)
                            total_time = registros[-1]["dt"] - registros[0]["dt"]
                            
                            # Cálculo do consumo (em litros) e custo
                            consumo_litros = total_distance / km_por_litro if km_por_litro > 0 else 0
                            custo = consumo_litros * preco_combustivel
                            
                            resultados.append({
                                "Veículo": vehicle_name,
                                "Distância (km)": round(total_distance, 2),
                                "Tempo": str(total_time),
                                "Km/L": km_por_litro,
                                "Consumo (L)": round(consumo_litros, 2),
                                "Custo (R$)": round(custo, 2)
                            })
                    
                    # Cria e exibe o DataFrame com os resultados
                    df = pd.DataFrame(resultados)
                    st.write("### Relatório Gerado", df)
                    
                    # Botão para download do relatório em CSV
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download CSV", csv, "relatorio_veiculos.csv", "text/csv")