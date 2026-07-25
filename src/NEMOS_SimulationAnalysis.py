import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyvista as pv
import re


class LoadSimulation:
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
        
        self.time_step=time

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

    def _list_boundaries(self):

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

    def _read_field_probe(
        self,
        probe_path,
        field,
        time=None,
        return_type="numpy"
    ):
    
       
    
        if os.path.isabs(probe_path):
            base_path = probe_path
        else:
            base_path = os.path.join(
                self.sim_path,
                "postProcessing",
                probe_path
            )
    
        if not os.path.exists(base_path):
            raise FileNotFoundError(base_path)
    
        contents = os.listdir(base_path)
    
        # -------------------------------------------------
        # Caso exista diretamente o arquivo
        # -------------------------------------------------
    
        if field in contents:
    
            file_list = [
                os.path.join(base_path, field)
            ]
    
        else:
    
            time_dirs = []
    
            for item in contents:
                try:
                    float(item)
                    time_dirs.append(item)
                except ValueError:
                    pass
    
            time_dirs = sorted(
                time_dirs,
                key=float
            )
    
            if len(time_dirs) == 0:
                raise ValueError(
                    "Nenhum diretório de tempo encontrado."
                )
    
            if time is not None:
    
                time_dirs = [str(time)]
    
                if not os.path.isdir(
                    os.path.join(base_path, time_dirs[0])
                ):
                    raise ValueError(
                        f"Time {time} não encontrado."
                    )
    
            file_list = [
                os.path.join(base_path, t, field)
                for t in time_dirs
            ]
    
        # -------------------------------------------------
        # Leitura
        # -------------------------------------------------
    
        times = []
        values = []
    
        labels = []
        labels_read = False
    
        for file_path in file_list:
    
            if not os.path.exists(file_path):
                continue
    
            with open(file_path, "r") as f:
    
                for line in f:
    
                    line = line.strip()
    
                    if not line:
                        continue
    
                    # -----------------------------------------
                    # Cabeçalho dos probes
                    # -----------------------------------------
    
                    if line.startswith("# Probe"):
    
                        if not labels_read:
    
                            m = re.search(
                                r"# Probe\s+(\d+)\s+\(([^)]+)\)",
                                line
                            )
    
                            if m:
    
                                probe = int(m.group(1))
                                coord = m.group(2)
    
                                while len(labels) <= probe:
                                    labels.append(None)
    
                                labels[probe] = (
                                    f"Probe {probe} ({coord})"
                                )
    
                        continue
    
                    if line.startswith("#"):
    
                        labels_read = True
                        continue
    
                    # -----------------------------------------
                    # Dados
                    # -----------------------------------------
    
                    line = (
                        line.replace("(", "")
                            .replace(")", "")
                    )
    
                    data = line.split()
    
                    times.append(float(data[0]))
    
                    values.append(
                        [float(v) for v in data[1:]]
                    )
    
            labels_read = True
    
        times = np.asarray(times)
        values = np.asarray(values)
    
        # Ordena por tempo
        idx = np.argsort(times)
    
        times = times[idx]
        values = values[idx]
    
        # Remove tempos repetidos
        times, unique = np.unique(
            times,
            return_index=True
        )
    
        values = values[unique]
    
        if values.shape[1] == 1:
            values = values[:, 0]
    
        if return_type == "dataframe":
    
            if values.ndim == 1:
    
                df = pd.DataFrame({
                    "Time": times,
                    field: values
                })
    
            else:
    
                cols = [
                    f"{field}_{i}"
                    for i in range(values.shape[1])
                ]
    
                df = pd.DataFrame(
                    values,
                    columns=cols
                )
    
                df.insert(0, "Time", times)
    
            return df, labels
    
        return times, values, labels


# =========================================================
# ANÁLISE
# =========================================================

class SimulationAnalysis:

    def __init__(self, sim):

        if sim is None:
            raise ValueError("sim não pode ser vazio")

        self.sim = sim

        self.internal_mesh = sim.internal_mesh
    def probe_to_excel(
        self,
        probe_path,
        field,
        output_excel=None,
        time=None
    ):
        """
        Lê um arquivo de probe do OpenFOAM e exporta para Excel.

        Parameters
        ----------
        probe_path : str
            Caminho da pasta do probe.
        field : str
            Nome do arquivo (T, U, p, etc.).
        output_excel : str, optional
            Caminho do arquivo .xlsx.
            Se None, utiliza "<field>.xlsx".
        time : float, optional
            Time step desejado. Se None, utiliza o último.

        Returns
        -------
        pandas.DataFrame
        """

        # reutiliza a função já existente
        df = self._read_field_probe(
            probe_path,
            field,
            time=time,
            return_type="dataframe"
        )

        # Nome padrão
        if output_excel is None:
            output_excel = f"{field}.xlsx"

        # Garante que a pasta exista
        out_dir = os.path.dirname(output_excel)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Exporta
        df.to_excel(output_excel, index=False)

        print(f"Arquivo salvo em: {output_excel}")

        return df

        
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
        sargs=dict(title_font_size=25,
                   vertical=True,
                   position_x=0.88,
                   position_y=0.15,
                   height=0.7,
                   label_font_size=20,
                   shadow=True,
                   n_labels=10,
                   )

        p = pv.Plotter(
            off_screen=True,
            window_size=(2400, 1800)
        )

        p.set_background("white")

        p.add_mesh(
            sliced,
            scalars=name,
            cmap="jet",
            clim=clim,
            scalar_bar_args=sargs
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
    
        times, values, labels = self.sim._read_field_probe(
            probe_path,
            field
        )
    
        values = np.asarray(values)
    
        # Número de componentes por probe
        if field == "U":
            ncomp = 3
    
        elif field in ["R", "ReStress", "UPrime2Mean"]:
            ncomp = 6
    
        else:
            ncomp = 1
    
        # ---------------------------------------------------------
        # Escalar
        # ---------------------------------------------------------
    
        if ncomp == 1:
    
            if values.ndim == 1:
                processed = values
    
            else:
                processed = values
    
        # ---------------------------------------------------------
        # Vetor ou tensor
        # ---------------------------------------------------------
    
        else:
    
            if values.ndim == 1:
    
                raise ValueError(
                    "Arquivo incompatível com o campo."
                )
    
            if values.shape[1] % ncomp != 0:
    
                raise ValueError(
                    f"Número de colunas incompatível para '{field}'."
                )
    
            n_probes = values.shape[1] // ncomp
    
            processed = values.reshape(
                len(times),
                n_probes,
                ncomp
            )
    
            # Magnitude da velocidade
            if field == "U" and magnitude:
    
                processed = np.linalg.norm(
                    processed,
                    axis=2
                )
    
            # RMS do tensor
            elif field in ["R", "ReStress", "UPrime2Mean"]:
    
                xx = processed[:, :, 0]
                yy = processed[:, :, 3]
                zz = processed[:, :, 5]
    
                processed = np.sqrt(
                    np.maximum(xx + yy + zz, 0)
                )
    
        # ---------------------------------------------------------
        # DataFrame
        # ---------------------------------------------------------
    
        if return_dataframe:
    
            if processed.ndim == 1:
    
                return pd.DataFrame({
                    "Time": times,
                    field: processed
                })
    
            elif processed.ndim == 2:
    
                cols = [
                    f"Probe_{i}"
                    for i in range(processed.shape[1])
                ]
    
                df = pd.DataFrame(
                    processed,
                    columns=cols
                )
    
                df.insert(0, "Time", times)
    
                return df
    
            else:
    
                data = {"Time": times}
    
                for p in range(processed.shape[1]):
    
                    for c in range(processed.shape[2]):
    
                        data[f"P{p}_{c}"] = processed[:, p, c]
    
                return pd.DataFrame(data)
    
        return times, processed, labels

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
    
        times, values, labels = self.get_probe_data(
            probe_path,
            field,
            magnitude=magnitude  # Sempre lê os dados originais
        )

    
        # -----------------------------------------------------
        # Campo escalar com um único probe
        # -----------------------------------------------------
        if values.ndim == 1:
    
            plt.figure(figsize=figsize)
            plt.plot(times, values, label="Probe 0")
    
            plt.title(f"Plot Probe - {field}")
            plt.xlabel("Time")
            plt.ylabel(field)
            plt.grid(True)
            plt.legend()
            plt.tight_layout()
            plt.show()
    
        # -----------------------------------------------------
        # Campo escalar com vários probes
        # -----------------------------------------------------
        elif values.ndim == 2:
    
            plt.figure(figsize=figsize)
    
            for p in range(values.shape[1]):
                plt.plot(
                    times,
                    values[:, p],
                    label=labels[p]
                )
    
            plt.title(f"Plot Probe - {field}")
            plt.xlabel("Time")
            plt.ylabel(field)
            plt.grid(True)
            plt.legend()
            plt.tight_layout()
            plt.show()
    
        # -----------------------------------------------------
        # Campo vetorial
        # -----------------------------------------------------
        elif values.ndim == 3:
    
            if magnitude:
    
                # Calcula a magnitude da velocidade
                vel_mag = np.linalg.norm(values, axis=2)
    
                plt.figure(figsize=figsize)
    
                for p in range(vel_mag.shape[1]):
                    plt.plot(
                        times,
                        vel_mag[:, p],
                        label=labels[p]
                    )
    
                plt.title(f"Plot Probe - {field}")
                plt.xlabel("Time")
                plt.ylabel(f"|{field}|")
                plt.grid(True)
                plt.legend()
                plt.tight_layout()
                plt.show()
    
            else:
    
                # Plota as componentes para cada probe
                componentes = ["x", "y", "z"]
    
                for p in range(values.shape[1]):
    
                    plt.figure(figsize=figsize)
    
                    for c in range(values.shape[2]):
                        plt.plot(
                            times,
                            values[:, p, c],
                            label=f"U{componentes[c]}"
                        )
    
                    plt.title(f"{field} - labels[p]")
                    plt.xlabel("Time")
                    plt.ylabel(field)
                    plt.grid(True)
                    plt.legend()
                    plt.tight_layout()
                    plt.show()
    def get_point_value(self, point_location, geometric_type=None,
                        interpolation_radius=0.1, field='T'):
    
        # Valida mesh
        if self.internal_mesh is None:
            raise ValueError("internal_mesh is not loaded")
        mesh = self.internal_mesh
    
        # Valida point_location
        try:
            point_location = np.array(point_location, dtype=float)
            if point_location.shape != (3,):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError("point_location must be a list or array with exactly 3 values [x, y, z]")
    
        # Valida raio
        if not isinstance(interpolation_radius, (int, float)) or interpolation_radius <= 0:
            raise ValueError("interpolation_radius must be a number greater than 0")
    
        # Valida campo
        if field not in mesh.array_names:
            raise KeyError(f"Field '{field}' not found in mesh. Available fields: {mesh.array_names}")
    
        # Monta geometria
        if geometric_type is None:
            point_mesh = pv.PolyData(point_location)
    
        elif geometric_type == 'sphere':
            point_mesh = pv.Sphere(radius=interpolation_radius, center=point_location)
    
        elif geometric_type == 'plane':
            point_mesh = pv.Plane(center=point_location, i_size=interpolation_radius,
                                                         j_size=interpolation_radius)
    
        elif geometric_type == 'box':
            x, y, z = point_location
            r = interpolation_radius
            point_mesh = pv.Box(bounds=[x-r, x+r, y-r, y+r, z-r, z+r])
    
        else:
            raise ValueError(f"geometric_type '{geometric_type}' not supported. "
                             f"Use: None, 'sphere', 'plane', 'box'")
    
        # Interpolação
        result = point_mesh.sample(mesh)
        values = result[field]
    
        # Detecta pontos fora da malha via máscara oficial do VTK
        valid_mask = result['vtkValidPointMask'].astype(bool)
        if not np.any(valid_mask):
            raise ValueError(f"Point {point_location.tolist()} is outside the mesh domain "
                             f"or returned no valid values")
    
        valid_values = values[valid_mask]
    
        return print({
            'mean':      float(np.mean(valid_values)),
            'min':       float(np.min(valid_values)),
            'max':       float(np.max(valid_values)),
            'std':       float(np.std(valid_values)),
            'n_points':  int(np.sum(valid_mask)),
            'n_invalid': int(np.sum(~valid_mask)),
            'field':     field
        })
class Regularization:

    def __init__(self, sim):
        if sim is None:
            raise ValueError("sim não pode ser vazio.")
        self.sim = sim


    def _internal_mesh(self):
        return self.sim.internal_mesh


    def reg2D(self, out_dir, n1, n2, plane="xy", value=None):

        mesh = self._internal_mesh()
        if mesh is None:
            raise ValueError("Malha interna não disponível.")

        current_time = self.sim.time_step
        time_str = f"{current_time:.3f}".replace(".", "_")

        plane = plane.strip().lower()

        x_min, x_max, y_min, y_max, z_min, z_max =mesh.bounds
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

        if data.ndim > 1:
            mag_name = f"{scalar}_mag"
            if mag_name not in plane_sampled.array_names:
                plane_sampled[mag_name] = np.linalg.norm(data, axis=1)
            scalar = mag_name

        p = plotter if plotter else pv.Plotter()
        sargs=dict(title_font_size=25,
                   vertical=True,
                   position_x=0.88,
                   position_y=0.15,
                   height=0.7,
                   label_font_size=20,
                   shadow=True,
                   n_labels=10,
                   )

        p.add_mesh(plane_sampled, scalars=scalar, cmap="jet", clim=clim,nan_opacity=0,scalar_bar_args=sargs)
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

        mesh = self._internal_mesh()
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
        sargs=dict(title_font_size=25,
                   vertical=True,
                   position_x=0.88,
                   position_y=0.15,
                   height=0.7,
                   label_font_size=20,
                   shadow=True,
                   n_labels=10,
                   )

        p.add_mesh(grid_sampled, scalars=scalar, cmap="jet", clim=clim,scalar_bar_args=sargs,opacity=0.85)

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