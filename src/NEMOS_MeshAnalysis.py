import os
import numpy as np
import pandas as pd
import pyvista as pv
from scipy.spatial import cKDTree 

class LoadSimulation:
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



    def __repr__(self):
        return (
            f"Simulation(path='{self.sim_path}', "
            f"time_step={self.time_step}, "
            f"n_boundaries={len(self.boundaries)})"
        )
class MeshVerification:
    """Fornece utilitários para visualização e análise de qualidade de malha."""
    
    def __init__(self, sim: LoadSimulation):
        self.sim = sim
        self.internal_mesh = sim.internal_mesh
        self.boundaries = sim.boundaries

        if self.internal_mesh is None:
            raise ValueError("A simulação não possui 'internalMesh'")

    # =========================
    # 🔹 UTILITÁRIO INTERNO
    # =========================
    def _get_slice_params(self, mesh, plane, value):
        x_min, x_max, y_min, y_max, z_min, z_max = mesh.bounds

        if plane == "xy":
            value = value if value is not None else (z_min + z_max) / 2
            return (0, 0, 1), (mesh.center[0], mesh.center[1], value), "xy"

        elif plane == "xz":
            value = value if value is not None else (y_min + y_max) / 2
            return (0, 1, 0), (mesh.center[0], value, mesh.center[2]), "xz"

        elif plane == "yz":
            value = value if value is not None else (x_min + x_max) / 2
            return (1, 0, 0), (value, mesh.center[1], mesh.center[2]), "yz"

        else:
            raise ValueError("Plano deve ser 'xy', 'xz' ou 'yz'")

    # =========================
    # 🔹 VISUALIZAÇÃO
    # =========================
    def plot_mesh(self, plane="xy", value=None):
        mesh = self.internal_mesh

        normal, origin, camera = self._get_slice_params(mesh, plane, value)
        sliced = mesh.slice(normal=normal, origin=origin)

        print("Células no slice:", sliced.n_cells)

        p = pv.Plotter(window_size=[400, 300])
        p.set_background("white")

        p.add_mesh(
            sliced,
            style="surface",
            color="lightblue",
            show_edges=True,
            edge_color="black",
            line_width=0.5
        )

        p.camera_position = camera
        p.show()

    def save_plot_mesh(self, filename="mesh.png", out_dir="", plane="xy", value=None):
        if not filename.endswith(".png"):
            filename += ".png"

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)

        mesh = self.internal_mesh
        normal, origin, camera = self._get_slice_params(mesh, plane, value)

        sliced = mesh.slice(normal=normal, origin=origin)

        p = pv.Plotter(off_screen=True, window_size=[400, 300])
        p.set_background("white")

        p.add_mesh(
            sliced,
            style="surface",
            color="lightblue",
            show_edges=True,
            edge_color="black",
            line_width=0.5,
        )

        p.camera_position = camera
        p.show(auto_close=False)
        p.screenshot(filepath)
        p.close()

        print(f"Imagem salva em: {filepath}")

    # =========================
    # 🔹 QUALIDADE
    # =========================
    def _compute_quality(self, measurement):
        measurement = measurement.lower()
        mesh = self.internal_mesh

        self.measurement = measurement

        if measurement == "volume":
            q_mesh = mesh.compute_cell_sizes()
            values = q_mesh.cell_data["Volume"]
            field_name = "Volume"
        else:
            q_mesh = mesh.cell_quality(quality_measure=measurement)
            values = q_mesh.cell_data[measurement]
            field_name = measurement

        self._quality_values = values
        self._field_name = field_name

        return q_mesh, field_name

    def quality_df(self, measurement):
        """
        Retorna um DataFrame contendo os valores da métrica de qualidade.
    
        Parameters
        ----------
        measurement : str
            Métrica de qualidade.
    
        Returns
        -------
        pandas.DataFrame
        """
        mesh=self.internal_mesh
        mesh_q, field_name = self._compute_quality(measurement)
    
        values = mesh_q.cell_data[field_name]
        centers = self.internal_mesh.cell_centers().points
    
        df = pd.DataFrame({
            "cell_id": np.arange(mesh.n_cells),
            self.measurement: values,
            "x": centers[:, 0],
            "y": centers[:, 1],
            "z": centers[:, 2],
            "cell_type": [
                pv.CellType(int(ct)).name
                for ct in mesh.celltypes
            ]
        })
    
        del mesh_q
    
        return df

    def quality_df_to_csv(self,df, filename="quality_df.csv", out_dir=""):
        if not filename.endswith(".csv"):
            filename += ".csv"

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)

        df.to_csv(filepath, index=False)

        print(f"O arquivo foi salvo em: {filepath}")

    def quality_plot(
        self,
        measurement,
        filename="quality.png",
        plane="xy",
        out_dir=".",
        value=None
    ):
    
        if not filename.endswith(".png"):
            filename += ".png"
    
        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)
    
        mesh_q, field_name = self._compute_quality(measurement)
    
        normal, origin, camera = self._get_slice_params(
            self.internal_mesh,
            plane,
            value
        )
    
        slice_mesh = mesh_q.slice(
            normal=normal,
            origin=origin
        )
    
        p = pv.Plotter(off_screen=True)
        p.set_background("white")
    
        sargs = dict(
            title_font_size=25,
            vertical=True,
            position_x=0.88,
            position_y=0.15,
            height=0.7,
            label_font_size=20,
            shadow=True,
            n_labels=10,
        )
    
        p.add_mesh(
            slice_mesh,
            scalars=field_name,
            cmap="jet",
            show_edges=False,
            scalar_bar_args=sargs
        )
    
        p.camera_position = camera
    
        p.show(auto_close=False)
        p.screenshot(filepath)
        p.close()
    
        print(f"Imagem salva em: {filepath}")
    
        del mesh_q

    # =========================
    # 🔹 GROWTH RATE
    # =========================
    def _compute_growth_rate(self):
        mesh = self.internal_mesh
    
        surface = mesh.extract_surface().compute_normals(
            cell_normals=True,
            point_normals=False,
            auto_orient_normals=True,
        )
    
        centers = surface.cell_centers().points
        normals = surface.cell_data["Normals"]
    
        # Normaliza os vetores normais
        norm_mag = np.linalg.norm(normals, axis=1)
        valid = norm_mag > 1e-6
        normals[valid] /= norm_mag[valid][:, None]
    
        # Área das células de superfície
        surface = surface.compute_cell_sizes(area=True)
        areas = surface.cell_data["Area"]
    
        valid_mask = (areas > 1e-16) & valid
    
        # Volume e centro das células volumétricas
        mesh_vol = mesh.compute_cell_sizes(volume=True)
        volumes = mesh_vol.cell_data["Volume"]
        volume_centers = mesh.cell_centers().points
    
        tree = cKDTree(volume_centers)
    
        eps = np.mean(np.sqrt(areas)) * 0.01
    
        probe_1 = centers[valid_mask] + normals[valid_mask] * eps
    
        _, idx1 = tree.query(probe_1, k=1)
        dy1 = volumes[idx1] / areas[valid_mask]
    
        probe_2 = probe_1 + normals[valid_mask] * dy1[:, None]
    
        _, idx2 = tree.query(probe_2, k=1)
        dy2 = volumes[idx2] / areas[valid_mask]
    
        growth = dy2 / dy1
    
        # Vetor do tamanho da malha
        growth_array = np.full(mesh.n_cells, np.nan)
    
        # Associa cada growth à célula correspondente
        growth_array[idx1] = growth
    
        mesh.cell_data["growth_rate"] = growth_array
    
        return growth_array
    
    def growth_rate_df(self):
        growth_rate=self._compute_growth_rate()
        centers=self.internal_mesh.cell_centers().points
        
        df=pd.DataFrame({
            "cell id": np.arange(self.internal_mesh.n_cells),
            "growth_rate": growth_rate,
            "x": centers[:,0],
            "y": centers[:,1],
            "z": centers[:,2]
            })
        return df

    def growth_rate_df_to_csv(self, filename="growth_rate.csv", out_dir=""):
        if not filename.endswith(".csv"):
            filename += ".csv"

        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)

        df = self.growth_rate_df()
        df.to_csv(filepath, index=False)

        print(f"O arquivo foi salvo em: {filepath}")

    def plot_growth_rate(
        self,
        filename="growth_rate.png",
        plane="xy",
        out_dir=".",
        value=None
    ):
        """
        Gera uma imagem do Growth Rate da malha.
    
        Parameters
        ----------
        filename : str, optional
            Nome do arquivo de saída.
        plane : {"xy", "xz", "yz"}, optional
            Plano de corte.
        out_dir : str, optional
            Diretório onde a imagem será salva.
        value : float, optional
            Coordenada do plano de corte. Caso None, utiliza o plano central.
        """
    
        if not filename.endswith(".png"):
            filename += ".png"
    
        os.makedirs(out_dir, exist_ok=True)
        filepath = os.path.join(out_dir, filename)
    
        # Calcula o Growth Rate
        growth_rate = self._compute_growth_rate()
    
        # Cria uma cópia da malha para não modificar a original
        mesh = self.internal_mesh.copy()
        mesh.cell_data["Growth Rate"] = growth_rate
    
        # Define plano de corte
        normal, origin, camera = self._get_slice_params(
            mesh,
            plane,
            value
        )
    
        slice_mesh = mesh.slice(
            normal=normal,
            origin=origin
        )
    
        # Configuração do plot
        p = pv.Plotter(off_screen=True)
        p.set_background("white")
    
        sargs = dict(
            title_font_size=25,
            vertical=True,
            position_x=0.88,
            position_y=0.15,
            height=0.7, 
            label_font_size=25,
            shadow=True,
            n_labels=10,
        )
    
        p.add_mesh(
            mesh,
            scalars="Growth Rate",
            cmap="jet",
            opacity=0.15,
            scalar_bar_args=sargs
        )
    
        p.camera_position = camera
    
        p.show(auto_close=False)
        p.screenshot(filepath)
        p.close()
    
        del mesh
    
        print(f"Imagem salva em: {filepath}")

