import Manager as nemos

# Retoma um lote (varredura) de onde parou.
# Basta apontar para a pasta raiz do caso (a que contem SIM_0, SIM_1, ...
# e a pasta scripts/) e rodar este script.
#
# Os SIM_i ja concluidos sao pulados e os incompletos continuam de onde
# pararam (reaproveitando os scripts ja gerados em scripts/).
#
# Para forcar a reexecucao de um SIM_i concluido, apague o marcador
# .nemos_done dentro da pasta SIM_i correspondente.

nemos.resume(r"C:\Users\pedro\Desktop\TCC1\Manager_Condition_Test")
