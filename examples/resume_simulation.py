import Simulation as nemos

# Retoma uma simulacao individual de onde parou.
# Basta usar a pasta do caso ja iniciado e rodar este script.
#
# Retoma cada estagio ja concluido automaticamente (malha, conversao,
# campos, decomposicao) e continua o solver a partir da ultima iteracao.
#
# Requer que a malha (Mesh_1.unv) ja tenha sido gerada — o caso comum de
# interrupcao durante o solver. Para interrupcoes antes da malha, rode
# novamente o script de geometria original (ele tambem retoma sozinho).
#
# Para forcar uma reexecucao limpa, apague o marcador .nemos_done (e, se
# quiser, Mesh_1.unv / a pasta 0/ / as pastas processor*).

nemos.resume(r"C:\Users\pedro\Desktop\TCC1\script_H_resume")
