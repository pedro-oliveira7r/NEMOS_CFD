"""
analysis_script_H.py
====================

Pre-requisitos
--------------
1. O caso precisa ter terminado (existe `.nemos_done` na pasta do caso).
2. Rodar em execucao paralela => reconstruir os tempos antes da analise:
       wsl bash -c "source /usr/lib/openfoam/openfoam2312/etc/bashrc && \
                    cd /mnt/c/.../script_H && reconstructPar"
   Sem isso so existem as pastas `processor*/` e o leitor nao enxerga
   nenhum timestep alem do 0.
3. `caso.foam` na raiz do caso (arquivo vazio) - este script cria caso falte.
4. Pacotes: pyvista, numpy, pandas, matplotlib, openpyxl (para .xlsx).

Uso
---
    cd src
    python analysis_script_H.py
"""

import os
import NEMOS_SimulationAnalysis as nemos

# =========================================================
# 0. CONFIGURACAO
# =========================================================

CASE_PATH = r"C:\Users\pedro\Desktop\TCC1\script_H"

OUT_DIR = os.path.join(CASE_PATH, "analysis")
IMG_DIR = os.path.join(OUT_DIR, "images")
DATA_DIR = os.path.join(OUT_DIR, "data")

# Nome da pasta do probe dentro de <case>/postProcessing/
PROBE_NAME = "probes"

# Plots interativos (pv.Plotter.show / plt.show) travam a execucao ate a
# janela ser fechada. Deixe False para uma rodada 100% automatica.
SHOW_INTERACTIVE = False

os.makedirs(IMG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# =========================================================
# 1. LoadSimulation - leitura do caso
# =========================================================

# time_step=None -> carrega o ultimo tempo escrito.
# Para um tempo especifico: nemos.LoadSimulation(CASE_PATH, time_step=20.0)
sim = nemos.LoadSimulation(CASE_PATH)

print("\n===== CASO CARREGADO =====")
print(sim)                                    # __repr__
print("Tempos disponiveis :", sim.available_times)
print("Tempo ativo        :", sim.time_step)
print("Contornos          :", sim._list_boundaries())
print("Campos disponiveis :", sim.internal_mesh.array_names)
print("Celulas / pontos   :", sim.internal_mesh.n_cells,
      "/", sim.internal_mesh.n_points)
print("Bounds             :", sim.internal_mesh.bounds)

# Acesso direto a um patch especifico (dict name -> pv.PolyData)
for patch_name, patch in list(sim.boundaries.items())[:3]:
    print(f"  patch '{patch_name}': {patch.n_cells} celulas")

# ---------------------------------------------------------
# 1.1 Troca de time step
# ---------------------------------------------------------
# ATENCAO: SimulationAnalysis e Regularization guardam a malha no momento
# da construcao. Faca todas as trocas de tempo ANTES de instancia-los -
# ou reinstancie os objetos depois de cada set_time().

if len(sim.available_times) > 1:

    sim.set_time(sim.available_times[-2])
    print(f"\nset_time -> {sim.time_step} "
          f"(T media = {sim.internal_mesh['T'].mean():.3f} K)")

    sim.set_time(sim.available_times[-1])
    print(f"set_time -> {sim.time_step} "
          f"(T media = {sim.internal_mesh['T'].mean():.3f} K)")


# Referencias uteis, calculadas a partir da propria malha
x_min, x_max, y_min, y_max, z_min, z_max = sim.internal_mesh.bounds

center = [
    (x_min + x_max) / 2,
    (y_min + y_max) / 2,
    (z_min + z_max) / 2,
]

T_field = sim.internal_mesh["T"]
CLIM_T = (float(T_field.min()), float(T_field.max()))


# =========================================================
# 2. SimulationAnalysis - cortes, sondas e valores pontuais
# =========================================================

analysis = nemos.SimulationAnalysis(sim)

# ---------------------------------------------------------
# 2.1 plot() - corte no plano + PNG (2400x1800, colormap jet)
# ---------------------------------------------------------
# O nome do arquivo sai como "<parametro>_<plano>_<tempo>.png".
# Campos vetoriais viram magnitude (U -> U_mag), tensores simetricos
# viram RMS (R -> R_rms) e TPrime2Mean vira T_rms automaticamente.

print("\n===== CORTES (SimulationAnalysis.plot) =====")

# Escalar, plano central automatico (value=None)
analysis.plot("T", out_dir=IMG_DIR, plane="xy")

# Escalar com plano e escala de cores explicitos
analysis.plot("T", out_dir=IMG_DIR, plane="xz",
              value=center[1], clim=CLIM_T)

# Vetorial -> plotado como |U|
analysis.plot("U", out_dir=IMG_DIR, plane="yz", value=center[0])

# Demais campos gerados pelo buoyantSimpleFoam
for parameter in ["p", "p_rgh", "k", "epsilon", "nut", "alphat"]:
    if parameter in sim.internal_mesh.array_names:
        analysis.plot(parameter, out_dir=IMG_DIR, plane="xy")

print(f"Imagens salvas em: {IMG_DIR}")


# ---------------------------------------------------------
# 2.2 get_point_value() - amostragem em um ponto / regiao
# ---------------------------------------------------------
# Imprime {mean, min, max, std, n_points, n_invalid, field}.
# Obs.: a funcao IMPRIME o dicionario e retorna None.

print("\n===== VALORES PONTUAIS (get_point_value) =====")

# Ponto exato (interpolacao em 1 ponto)
print("Centro da sala, T:")
analysis.get_point_value(center, field="T")

# Esfera: media de T num raio de 15 cm em torno do ponto
print("Esfera r=0.15 m, T:")
analysis.get_point_value(center, geometric_type="sphere",
                         interpolation_radius=0.15, field="T")

# Plano: quadrado de 0.5 m de lado centrado no ponto
print("Plano 0.5 m, T:")
analysis.get_point_value(center, geometric_type="plane",
                         interpolation_radius=0.5, field="T")

# Caixa: cubo de lado 2*r centrado no ponto
print("Caixa r=0.25 m, p:")
analysis.get_point_value(center, geometric_type="box",
                         interpolation_radius=0.25, field="p")

# Campos vetoriais tambem funcionam - as estatisticas sao calculadas
# sobre todas as componentes juntas (Ux, Uy e Uz no mesmo saco).
print("Esfera r=0.20 m, U (componentes agregadas):")
analysis.get_point_value(center, geometric_type="sphere",
                         interpolation_radius=0.20, field="U")

# =========================================================
# 3. Regularization - malha estruturada + exportacao
# =========================================================
# Reamostra a malha nao estruturada do OpenFOAM numa grade regular,
# exporta a tabela (X, Y, Z, T, Ux, Uy, Uz, U) e plota o resultado.
# Pontos fora do dominio (dentro dos manequins, por exemplo) viram NaN
# e sao descartados do DataFrame.

reg = nemos.Regularization(sim)

# ---------------------------------------------------------
# 3.1 reg2D - grade 2D num plano
# ---------------------------------------------------------

print("\n===== REGULARIZACAO 2D =====")

# Plano central em XY -> salva Sim_points_2D_xy_t<tempo>.xlsx
df_xy, plane_xy = reg.reg2D(out_dir=DATA_DIR, n1=120, n2=120, plane="xy")
print(df_xy[["T", "U"]].describe())

# Plano XZ numa altura especifica (ex.: altura da cabeca)
df_xz, plane_xz = reg.reg2D(out_dir=DATA_DIR, n1=120, n2=120,
                            plane="xz", value=center[1])

# Plano YZ
df_yz, plane_yz = reg.reg2D(out_dir=DATA_DIR, n1=100, n2=100,
                            plane="yz", value=center[0])

# PNG do plano regularizado (escalar ou vetorial - U vira U_mag sozinho)
reg.save_plot_2D_reg(plane_xy, scalar="T", filename="reg2D_T_xy.png",
                     out_dir=IMG_DIR, clim=CLIM_T)

reg.save_plot_2D_reg(plane_xy, scalar="U", filename="reg2D_U_xy.png",
                     out_dir=IMG_DIR)

reg.save_plot_2D_reg(plane_xz, scalar="T", filename="reg2D_T_xz.png",
                     out_dir=IMG_DIR, clim=CLIM_T)

# Versao interativa (janela do pyvista)
if SHOW_INTERACTIVE:
    reg.plot_2D(plane_xy, scalar="T", clim=CLIM_T)
    reg.plot_2D(plane_yz, scalar="U")


# ---------------------------------------------------------
# 3.2 reg3D - grade 3D no volume inteiro
# ---------------------------------------------------------
# Cuidado com nx*ny*nz: 60^3 = 216 mil pontos ja e pesado.

print("\n===== REGULARIZACAO 3D =====")

df_3d, grid_3d = reg.reg3D(nx=50, ny=50, nz=50, out_dir=DATA_DIR)
print("Pontos validos no volume:", len(df_3d))
print(df_3d[["T", "U"]].describe())

reg.save_plot_3D_reg(grid_3d, scalar="T", filename="reg3D_T.png",
                     out_dir=IMG_DIR, clim=CLIM_T)

reg.save_plot_3D_reg(grid_3d, scalar="U", filename="reg3D_U.png",
                     out_dir=IMG_DIR)

if SHOW_INTERACTIVE:
    reg.plot_reg_3D(grid_3d, scalar="T", clim=CLIM_T)


# =========================================================
# 4. Comparacao entre time steps (opcional)
# =========================================================
# Como os objetos de analise congelam a malha, cada tempo exige uma nova
# instancia. Util para acompanhar a convergencia do campo de temperatura.

print("\n===== EVOLUCAO TEMPORAL =====")

for t in sim.available_times[-3:]:

    sim_t = nemos.LoadSimulation(CASE_PATH, time_step=t)
    analysis_t = nemos.SimulationAnalysis(sim_t)

    analysis_t.plot("T", out_dir=IMG_DIR, plane="xy", clim=CLIM_T)

    print(f"t = {t:>8} | T media = {sim_t.internal_mesh['T'].mean():.3f} K")


print(f"\nAnalise concluida. Resultados em: {OUT_DIR}")
