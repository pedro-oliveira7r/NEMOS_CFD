# -*- coding: utf-8 -*-
"""
Created on Sat May 23 13:38:23 2026

@author: gabri
"""

import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyvista as pv


class Simulation:
    """
    Representa uma simulação OpenFOAM.
    """

    def __init__(self, sim_path, time_step=None):

        if not sim_path:
            raise ValueError("sim_path não pode estar vazio")

        self.sim_path = sim_path

        base = os.path.join(sim_path, "caso.foam")

        if not os.path.exists(base):
            raise FileNotFoundError(f"{base} não encontrado")

        self.case = pv.OpenFOAMReader(base)

        times = self.case.time_values

        if not times:
            raise ValueError("Nenhum timestep encontrado")

        if time_step is None:
            self.time_step = times[-1]
        else:

            if not np.isclose(times, time_step).any():
                raise ValueError(
                    f"Time step inválido: {time_step}"
                )

            self.time_step = time_step

        self.available_times = list(times)

        self.case.set_active_time_value(
            self.time_step
        )

        self.mesh = self.case.read()

        self.internal_mesh = self._get_internal_mesh()

        self.boundaries = self._get_boundaries()

    # =====================================================
    # TIME
    # =====================================================

    def set_time(self, time):

        self.case.set_active_time_value(time)

        self.mesh = self.case.read()

        self.internal_mesh = self._get_internal_mesh()

        self.boundaries = self._get_boundaries()

    # =====================================================
    # MESH
    # =====================================================

    def _get_internal_mesh(self):

        try:
            return self.mesh["internalMesh"]

        except KeyError:
            return None

    def _get_boundaries(self):

        boundaries = {}

        for name in self.mesh.keys():

            if name != "internalMesh":
                boundaries[name] = self.mesh[name]

        return boundaries

    def get_boundary(self, name):

        return self.boundaries.get(name, None)

    def list_boundaries(self):

        return list(self.boundaries.keys())

    # =====================================================
    # REPRESENTAÇÃO
    # =====================================================

    def __repr__(self):

        return (
            f"Simulation("
            f"path='{self.sim_path}', "
            f"time_step={self.time_step}, "
            f"n_boundaries={len(self.boundaries)}"
            f")"
        )

    # =====================================================
    # PROBES
    # =====================================================

    def read_field_probe(
        self,
        probe_path,
        field,
        time=None,
        return_type="numpy"
    ):
        """
        Lê qualquer variável de probe.
        """

        # -------------------------------------------------
        # caminho
        # -------------------------------------------------

        if os.path.isabs(probe_path):

            base_path = probe_path

        else:

            base_path = os.path.join(
                self.sim_path,
                "postProcessing",
                probe_path
            )

        if not os.path.exists(base_path):

            raise FileNotFoundError(
                f"Caminho não encontrado: {base_path}"
            )

        contents = os.listdir(base_path)

        # -------------------------------------------------
        # timestep
        # -------------------------------------------------

        if field in contents:

            selected_path = base_path

        else:

            time_dirs = []

            for item in contents:

                try:
                    float(item)
                    time_dirs.append(item)

                except:
                    pass

            time_dirs = sorted(
                time_dirs,
                key=lambda x: float(x)
            )

            if not time_dirs:

                raise ValueError(
                    "Nenhum timestep encontrado"
                )

            if time is None:

                selected_time = time_dirs[-1]

            else:

                time_str = str(time)

                if time_str not in time_dirs:

                    raise ValueError(
                        f"Time '{time}' não encontrado.\n"
                        f"Disponíveis: {time_dirs}"
                    )

                selected_time = time_str

            selected_path = os.path.join(
                base_path,
                selected_time
            )

        # -------------------------------------------------
        # arquivo
        # -------------------------------------------------

        file_path = os.path.join(
            selected_path,
            field
        )

        if not os.path.exists(file_path):

            raise FileNotFoundError(
                f"Arquivo não encontrado: {file_path}"
            )

        # -------------------------------------------------
        # leitura
        # -------------------------------------------------

        times = []

        values = []

        with open(file_path, "r") as f:

            for line in f:

                line = line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                line = (
                    line.replace("(", "")
                    .replace(")", "")
                )

                data = line.split()

                times.append(float(data[0]))

                row = [
                    float(v)
                    for v in data[1:]
                ]

                values.append(row)

        times = np.asarray(times)

        values = np.asarray(values)

        # escalar
        if values.shape[1] == 1:
            values = values[:, 0]

        # -------------------------------------------------
        # dataframe
        # -------------------------------------------------

        if return_type == "dataframe":

            if values.ndim == 1:

                df = pd.DataFrame({
                    "Time": times,
                    field: values
                })

            else:

                ncomp = values.shape[1]

                if ncomp == 3:

                    cols = [
                        f"{field}_x",
                        f"{field}_y",
                        f"{field}_z",
                    ]

                elif ncomp == 6:

                    cols = [
                        f"{field}_xx",
                        f"{field}_xy",
                        f"{field}_xz",
                        f"{field}_yy",
                        f"{field}_yz",
                        f"{field}_zz",
                    ]

                else:

                    cols = [
                        f"{field}_{i}"
                        for i in range(ncomp)
                    ]

                df = pd.DataFrame(
                    values,
                    columns=cols
                )

                df.insert(0, "Time", times)

            return df

        return times, values


# =========================================================
# ANÁLISE
# =========================================================

class SimulationAnalysis:

    def __init__(self, sim):

        if sim is None:
            raise ValueError("sim não pode ser vazio")

        self.sim = sim

        self.internal_mesh = sim.internal_mesh

    # =====================================================
    # PLOT 3D / SLICE
    # =====================================================

    def plot(
        self,
        parameter,
        out_dir,
        plane="xy",
        value=None,
        clim=None
    ):

        mesh = self.internal_mesh

        if mesh is None:
            raise ValueError("Mesh vazio")

        plane = plane.lower()

        x_min, x_max, y_min, y_max, z_min, z_max = (
            mesh.bounds
        )

        # -------------------------------------------------
        # plano
        # -------------------------------------------------

        if plane == "xy":

            if value is None:
                value = (z_min + z_max) / 2

            normal = (0, 0, 1)

            origin = (
                (x_min + x_max) / 2,
                (y_min + y_max) / 2,
                value,
            )

        elif plane == "xz":

            if value is None:
                value = (y_min + y_max) / 2

            normal = (0, 1, 0)

            origin = (
                (x_min + x_max) / 2,
                value,
                (z_min + z_max) / 2,
            )

        elif plane == "yz":

            if value is None:
                value = (x_min + x_max) / 2

            normal = (1, 0, 0)

            origin = (
                value,
                (y_min + y_max) / 2,
                (z_min + z_max) / 2,
            )

        else:

            raise ValueError(
                "Plano inválido"
            )

        sliced = mesh.slice(
            normal=normal,
            origin=origin
        )

        data = np.asarray(
            sliced[parameter]
        )

        # -------------------------------------------------
        # escalar
        # -------------------------------------------------

        if data.ndim == 1:

            if parameter == "TPrime2Mean":

                processed = np.sqrt(
                    np.maximum(data, 0)
                )

                name = "T_rms"

                sliced[name] = processed

            else:

                name = parameter

        # -------------------------------------------------
        # vetor/tensor
        # -------------------------------------------------

        else:

            ncomp = data.shape[1]

            # vetor
            if ncomp == 3:

                processed = np.linalg.norm(
                    data,
                    axis=1
                )

                name = f"{parameter}_mag"

                sliced[name] = processed

            # tensor simétrico
            elif ncomp == 6:

                xx = data[:, 0]
                yy = data[:, 3]
                zz = data[:, 5]

                processed = np.sqrt(
                    np.maximum(
                        xx + yy + zz,
                        0
                    )
                )

                name = f"{parameter}_rms"

                sliced[name] = processed

            else:

                processed = data[:, 0]

                name = f"{parameter}_0"

                sliced[name] = processed

        # -------------------------------------------------
        # plot
        # -------------------------------------------------

        os.makedirs(out_dir, exist_ok=True)

        p = pv.Plotter(
            off_screen=True,
            window_size=(2400, 1800)
        )

        p.set_background("white")

        p.add_mesh(
            sliced,
            scalars=name,
            cmap="jet",
            clim=clim
        )

        p.camera_position = plane

        time_str = (
            f"{self.sim.case.active_time_value:.3f}"
            .replace(".", "_")
        )

        filename = (
            f"{parameter}_{plane}_{time_str}.png"
        )

        p.screenshot(
            os.path.join(out_dir, filename)
        )

        p.close()

    # =====================================================
    # PROBES
    # =====================================================

    def get_probe_data(
        self,
        probe_path,
        field,
        magnitude=False,
        rms=False,
        return_dataframe=False
    ):

        times, values = self.sim.read_field_probe(
            probe_path,
            field
        )

        values = np.asarray(values)

        # escalar
        if values.ndim == 1:

            processed = values

        # vetor
        elif values.shape[1] == 3:

            if magnitude:

                processed = np.linalg.norm(
                    values,
                    axis=1
                )

            else:

                processed = values

        # tensor
        elif values.shape[1] == 6:

            xx = values[:, 0]
            yy = values[:, 3]
            zz = values[:, 5]

            processed = np.sqrt(
                np.maximum(
                    xx + yy + zz,
                    0
                )
            )

        else:

            processed = values

        # dataframe
        if return_dataframe:

            if processed.ndim == 1:

                return pd.DataFrame({
                    "Time": times,
                    field: processed
                })

            cols = [
                f"{field}_{i}"
                for i in range(processed.shape[1])
            ]

            df = pd.DataFrame(
                processed,
                columns=cols
            )

            df.insert(0, "Time", times)

            return df

        return times, processed

    # =====================================================
    # PLOT PROBE
    # =====================================================

    def plot_probe(
        self,
        probe_path,
        field,
        magnitude=False,
        figsize=(10, 5)
    ):

        times, values = self.get_probe_data(
            probe_path,
            field,
            magnitude=magnitude
        )

        plt.figure(figsize=figsize)

        # escalar
        if values.ndim == 1:

            plt.plot(times, values)

        # multi componente
        else:

            for i in range(values.shape[1]):

                plt.plot(
                    times,
                    values[:, i],
                    label=f"{field}_{i}"
                )

            plt.legend()

        plt.title(field)

        plt.xlabel("Time")

        plt.ylabel(field)

        plt.grid()

        plt.tight_layout()

        plt.show()
sim=Simulation("D:\Documentos-IC\SIM_4")
teste=SimulationAnalysis(sim)
teste.plot(parameter="p_rgh",out_dir="D:\Documentos-IC\SIM_4",value=1.5,plane="xy")