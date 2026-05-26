# -*- coding: utf-8 -*-
"""
Created on Mon Apr 13 08:54:47 2026

@author: gabri
"""

import os
import numpy as np
import pandas as pd
import pyvista as pv
import matplotlib.pyplot as plt


class Simulation:
    """Representa uma simulação OpenFOAM e fornece acesso aos dados."""

    def __init__(self, sim_path: str, time_step: float | None = None):

        if not sim_path:
            raise ValueError("sim_path não pode estar vazio")

        self.sim_path = sim_path

        
        self._foam_file = os.path.join(sim_path, "caso.foam")
        if not os.path.exists(self._foam_file):
            raise FileNotFoundError(f"{self._foam_file} não encontrado")

       
        self.case = pv.OpenFOAMReader(self._foam_file)

        self.available_times = list(self.case.time_values)
        if not self.available_times:
            raise ValueError("Nenhum time step encontrado")

        
        if time_step is None:
            self.time_step = self.available_times[-1]
        else:
            self._validate_time(time_step)
            self.time_step = time_step

      
        self._load_time(self.time_step)



    def _validate_time(self, time):
        if not np.isclose(self.available_times, time).any():
            raise ValueError(
                f"Time step inválido: {time}\n"
                f"Disponíveis: {self.available_times}"
            )

    def _load_time(self, time):
        """Carrega dados de um determinado tempo."""
        self.case.set_active_time_value(time)
        self.mesh = self.case.read()
        self.internal_mesh = self._get_internal_mesh()
        self.boundaries = self._get_boundaries()
        self.time_step = time

    def set_time(self, time):
        """Atualiza o tempo da simulação (seguro)."""
        self._validate_time(time)
        self._load_time(time)



    def _get_internal_mesh(self):
        try:
            return self.mesh["internalMesh"]
        except KeyError:
            return None

    def _get_boundaries(self):
        return {
            name: self.mesh[name]
            for name in self.mesh.keys()
            if name != "internalMesh"
        }

    def get_boundary(self, name: str):
        return self.boundaries.get(name)

    def list_boundaries(self):
        return list(self.boundaries.keys())



    def read_probe(self, probe_path, field="U", time=None):

        base_path = (
            probe_path
            if os.path.isabs(probe_path)
            else os.path.join(self.sim_path, "postProcessing", probe_path)
        )

        if not os.path.exists(base_path):
            raise FileNotFoundError(f"Caminho não encontrado: {base_path}")

        contents = os.listdir(base_path)

        # 🔹 caso direto
        if field in contents:
            selected_path = base_path
        else:
            time_dirs = sorted(contents, key=lambda x: float(x))

            if not time_dirs:
                raise ValueError("Nenhum timestep encontrado")

            if time is None:
                selected_time = time_dirs[-1]
            else:
                selected_time = str(time)
                if selected_time not in time_dirs:
                    raise ValueError(
                        f"Time '{time}' não encontrado.\n"
                        f"Disponíveis: {time_dirs}"
                    )

            selected_path = os.path.join(base_path, selected_time)

        file_path = os.path.join(selected_path, field)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        times, values = [], []

        with open(file_path, "r") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue

                data = line.replace("(", "").replace(")", "").split()
                times.append(float(data[0]))
                values.append([float(v) for v in data[1:]])

        return np.array(times), np.array(values)

    def read_U_T(self, probe_path, time=None):
        tU, U = self.read_probe(probe_path, field="U", time=time)
        tT, T = self.read_probe(probe_path, field="T", time=time)
        return tU, U, tT, T



    def __repr__(self):
        return (
            f"Simulation(path='{self.sim_path}', "
            f"time_step={self.time_step}, "
            f"n_boundaries={len(self.boundaries)})"
        )
class SimulationAnalysis:
    """Fornece métodos de análise e visualização para uma simulação OpenFOAM."""

    def __init__(self, sim):
        if sim is None:
            raise ValueError("simulation não pode ser vazia!")
        self.sim = sim

    @property
    def internal_mesh(self):
        return self.sim.internal_mesh

    def plot(self, parameter, out_dir, plane="xy", value=None, clim=None):

        mesh = self.internal_mesh
        if mesh is None:
            raise ValueError("Mesh não pode ser vazio.")

        parameter_input = parameter.strip()
        parameter_lower = parameter_input.lower()

        current_time = self.sim.time_step
        plane = plane.strip().lower()

        x_min, x_max, y_min, y_max, z_min, z_max = mesh.bounds

        fig_size = (2400, 1800)

        scalar_bar = dict(
            title_font_size=45,
            label_font_size=40,
            width=0.08,
            height=0.6,
            vertical=True,
            position_x=0.88,
            position_y=0.2,
            fmt="%.2f",
        )

        if plane == "xy":
            value = value if value is not None else (z_min + z_max) / 2
            normal_p = (0, 0, 1)
            origin_p = ((x_min + x_max)/2, (y_min + y_max)/2, value)
            camera_p = "xy"

        elif plane == "xz":
            value = value if value is not None else (y_min + y_max) / 2
            normal_p = (0, 1, 0)
            origin_p = ((x_min + x_max)/2, value, (z_min + z_max)/2)
            camera_p = "xz"

        elif plane == "yz":
            value = value if value is not None else (x_min + x_max) / 2
            normal_p = (1, 0, 0)
            origin_p = (value, (y_min + y_max)/2, (z_min + z_max)/2)
            camera_p = "yz"

        else:
            raise ValueError("Plano deve ser 'xy', 'xz' ou 'yz'")

        sliced_mesh = mesh.slice(normal=normal_p, origin=origin_p)

        available = sliced_mesh.array_names

        if parameter_input in available:
            param_name = parameter_input
        elif parameter_input.upper() in available:
            param_name = parameter_input.upper()
        elif parameter_lower in available:
            param_name = parameter_lower
        else:
            raise ValueError(f"Variável '{parameter}' não encontrada.\n{available}")

        data = sliced_mesh[param_name]

        if data.ndim == 2:
            mag_name = f"{param_name}_mag"
            sliced_mesh[mag_name] = np.linalg.norm(data, axis=1)
            scalar_plot = mag_name
            title = f"{param_name} magnitude"
        else:
            scalar_plot = param_name
            title = param_name

        time_str = f"{current_time:.3f}".replace(".", "_")

        p = pv.Plotter(off_screen=True, window_size=fig_size)
        p.set_background("white")

        p.add_mesh(
            sliced_mesh,
            scalars=scalar_plot,
            cmap="jet",
            clim=clim,
            scalar_bar_args={**scalar_bar, "title": title},
        )

        p.camera_position = camera_p
        p.render()

        os.makedirs(out_dir, exist_ok=True)
        filename = f"{param_name}_{plane}_t{time_str}.png"
        p.screenshot(os.path.join(out_dir, filename))

        p.close()


    def read_U_T_probe(self, probe_path):
        return self.sim.read_U_T(probe_path)

    def read_U_T_rms_probe(self, probe_path):

        tU, UPrime2Mean = self.sim.read_probe(probe_path, field="UPrime2Mean")
        tT, TPrime2Mean = self.sim.read_probe(probe_path, field="TPrime2Mean")

        UPrime2Mean = np.asarray(UPrime2Mean)
        TPrime2Mean = np.squeeze(np.asarray(TPrime2Mean))

        uu = UPrime2Mean[:, 0]
        vv = UPrime2Mean[:, 3]
        ww = UPrime2Mean[:, 5]

        U_rms = np.sqrt(uu + vv + ww)

        TPrime2Mean[TPrime2Mean < 0] = 0
        T_rms = np.sqrt(TPrime2Mean)

        return tU, U_rms, tT, T_rms

    def plot_UT_rms(self, probe_path):

        tU, U_rms, tT, T_rms = self.read_U_T_rms_probe(probe_path)

        fig, axs = plt.subplots(2, 1, figsize=(10, 8))

        axs[0].plot(tU, U_rms, "r")
        axs[0].set_title("Velocity RMS")
        axs[0].grid()

        axs[1].plot(tT, T_rms, "b")
        axs[1].set_title("Temperature RMS")
        axs[1].grid()

        plt.tight_layout()
        plt.show()

    def plot_UT_instant(self, probe_path):

        tU, U, tT, T = self.read_U_T_probe(probe_path)

        U = np.asarray(U)
        Umag = np.linalg.norm(U, axis=1)

        fig, axs = plt.subplots(2, 1, figsize=(10, 8))

        axs[0].plot(tU, Umag, "r")
        axs[0].set_title("Velocity Magnitude")
        axs[0].grid()

        axs[1].plot(tT, T, "b")
        axs[1].set_title("Temperature")
        axs[1].grid()

        plt.tight_layout()
        plt.show()



class Regularization:

    def __init__(self, sim):
        if sim is None:
            raise ValueError("sim não pode ser vazio.")
        self.sim = sim

    @property
    def internal_mesh(self):
        return self.sim.internal_mesh


    def reg2D(self, out_dir, n1, n2, plane="xy", value=None):

        mesh = self.internal_mesh
        if mesh is None:
            raise ValueError("Malha interna não disponível.")

        current_time = self.sim.time_step
        time_str = f"{current_time:.3f}".replace(".", "_")

        plane = plane.strip().lower()

        x_min, x_max, y_min, y_max, z_min, z_max = mesh.bounds

        if plane == "xy":
            value = value if value is not None else (z_min + z_max) / 2
            x = np.linspace(x_min, x_max, n1)
            y = np.linspace(y_min, y_max, n2)
            X, Y = np.meshgrid(x, y, indexing="ij")
            Z = np.full_like(X, value)

        elif plane == "xz":
            value = value if value is not None else (y_min + y_max) / 2
            x = np.linspace(x_min, x_max, n1)
            z = np.linspace(z_min, z_max, n2)
            X, Z = np.meshgrid(x, z, indexing="ij")
            Y = np.full_like(X, value)

        elif plane == "yz":
            value = value if value is not None else (x_min + x_max) / 2
            y = np.linspace(y_min, y_max, n1)
            z = np.linspace(z_min, z_max, n2)
            Y, Z = np.meshgrid(y, z, indexing="ij")
            X = np.full_like(Y, value)

        else:
            raise ValueError("Plano deve ser 'xy','xz' ou 'yz'")

        plane_structured = pv.StructuredGrid(X, Y, Z)
        plane_sampled = plane_structured.sample(mesh)

        plane_sampled.field_data["plane"] = np.array([plane])
        plane_sampled.field_data["value"] = np.array([value])

        valid_mask = plane_sampled["vtkValidPointMask"].astype(bool)

        points = plane_sampled.points
        T = np.asarray(plane_sampled["T"])
        U = np.asarray(plane_sampled["U"])

        T[~valid_mask] = np.nan
        U[~valid_mask, :] = np.nan

        df = pd.DataFrame({
            "X": points[valid_mask, 0],
            "Y": points[valid_mask, 1],
            "Z": points[valid_mask, 2],
            "T": T[valid_mask],
            "Ux": U[valid_mask, 0],
            "Uy": U[valid_mask, 1],
            "Uz": U[valid_mask, 2],
        })

        df["U"] = np.linalg.norm(df[["Ux", "Uy", "Uz"]].values, axis=1)

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, f"Sim_points_2D_{plane}_t{time_str}.xlsx")
        df.to_excel(filepath, index=False)

        return df, plane_sampled


    def _build_plot(self, plane_sampled, scalar="T", clim=None, plotter=None):

        if scalar not in plane_sampled.array_names:
            raise ValueError(f"Variável '{scalar}' não encontrada.")

        data = plane_sampled[scalar]

        if data.ndim == 2:
            mag_name = f"{scalar}_mag"
            if mag_name not in plane_sampled.array_names:
                plane_sampled[mag_name] = np.linalg.norm(data, axis=1)
            scalar = mag_name

        p = plotter if plotter else pv.Plotter()

        p.add_mesh(plane_sampled, scalars=scalar, cmap="jet", clim=clim)
        p.camera_position = str(plane_sampled.field_data["plane"][0])

        return p

    def plot_2D(self, plane_sampled, scalar="T", clim=None):
        p = self._build_plot(plane_sampled, scalar, clim)
        p.show()

    def save_plot_2D_reg(self, plane_sampled, scalar="T", filename="2D.png", out_dir="", clim=None):

        if not filename.endswith(".png"):
            filename += ".png"

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)

        p = pv.Plotter(off_screen=True)
        self._build_plot(plane_sampled, scalar, clim, plotter=p)

        p.render()
        p.screenshot(filepath)
        p.close()

        print(f"Imagem salva em: {filepath}")


    def reg3D(self, nx, ny, nz, out_dir):

        mesh = self.internal_mesh
        if mesh is None:
            raise ValueError("Malha interna não disponível")

        current_time = self.sim.time_step
        time_str = f"{current_time:.3f}".replace(".", "_")

        x_min, x_max, y_min, y_max, z_min, z_max = mesh.bounds

        x = np.linspace(x_min, x_max, nx)
        y = np.linspace(y_min, y_max, ny)
        z = np.linspace(z_min, z_max, nz)

        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")

        grid = pv.StructuredGrid(X, Y, Z)
        grid_sampled = grid.sample(mesh)

        valid_mask = grid_sampled["vtkValidPointMask"].astype(bool)

        points = grid_sampled.points
        T = np.asarray(grid_sampled["T"])
        U = np.asarray(grid_sampled["U"])

        T[~valid_mask] = np.nan
        U[~valid_mask, :] = np.nan

        df = pd.DataFrame({
            "X": points[valid_mask, 0],
            "Y": points[valid_mask, 1],
            "Z": points[valid_mask, 2],
            "T": T[valid_mask],
            "Ux": U[valid_mask, 0],
            "Uy": U[valid_mask, 1],
            "Uz": U[valid_mask, 2],
        })

        df["U"] = np.linalg.norm(df[["Ux", "Uy", "Uz"]].values, axis=1)

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, f"Sim_points_3D_t{time_str}.csv")
        df.to_csv(filepath, index=False)

        grid_sampled.field_data["nx"] = np.array([nx])
        grid_sampled.field_data["ny"] = np.array([ny])
        grid_sampled.field_data["nz"] = np.array([nz])

        return df, grid_sampled


    def _build_plot_3D(self, grid_sampled, scalar="T", clim=None, plotter=None):

        if scalar not in grid_sampled.array_names:
            raise ValueError(f"Variável '{scalar}' não encontrada.")

        data = grid_sampled[scalar]

        if data.ndim == 2:
            mag_name = f"{scalar}_mag"
            if mag_name not in grid_sampled.array_names:
                grid_sampled[mag_name] = np.linalg.norm(data, axis=1)
            scalar = mag_name

        p = plotter if plotter else pv.Plotter()

        p.add_mesh(grid_sampled, scalars=scalar, cmap="jet", clim=clim)

        return p

    def plot_reg_3D(self, grid_sampled, scalar="T", clim=None):
        p = self._build_plot_3D(grid_sampled, scalar, clim)
        p.show()

    def save_plot_3D_reg(self, grid_sampled, scalar="T", filename="3D.png", out_dir="", clim=None):

        if not filename.endswith(".png"):
            filename += ".png"

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)

        p = pv.Plotter(off_screen=True)
        self._build_plot_3D(grid_sampled, scalar, clim, plotter=p)

        p.render()
        p.screenshot(filepath)
        p.close()

        print(f"Imagem salva em: {filepath}")

