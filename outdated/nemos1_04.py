import math
from os import name
import sys
import time

import GEOM
import SALOMEDS
import SMESH
import salome
import salome_notebook
from salome.geom import geomBuilder
from salome.smesh import smeshBuilder


def salome_start():
    salome.salome_init()
    notebook = salome_notebook.NoteBook()
    sys.path.insert(0, r'C:/Users/Usuario/Desktop/Openfoam')

    return notebook


def salome_update():
    if salome.sg.hasDesktop():
        salome.sg.updateObjBrowser()


class Salome_Env:

    def __init__(self, path=None):
        salome.salome_init()
        self.notebook = salome_notebook.NoteBook()

        if path is None:
            sys.path.insert(0, r'C:/Users/Usuario/Desktop/Openfoam')
        else:
            sys.path.insert(0, path)

        self.geompy = geomBuilder.New()
        self.O = self.geompy.MakeVertex(0, 0, 0)
        self.OX = self.geompy.MakeVectorDXDYDZ(1, 0, 0)
        self.OY = self.geompy.MakeVectorDXDYDZ(0, 1, 0)
        self.OZ = self.geompy.MakeVectorDXDYDZ(0, 0, 1)
        self.boxList = []
        self.room = None


class Room:

    def __init__(self, salome_env, dx=3.000, dy=3.000, dz=3.000, name='Room'):
        self.salome_env = salome_env
        self.name = name
        self.H = dy
        aux = [dx, dy, dz]
        aux.sort()
        self.area = 0.8 * aux[0] * aux[1]
        self.n = 0  # counter
        self.obj_list = []
        self.outlet_faces = []
        self.inlet_faces = []
        self.wall_faces = []
        self.faces_groups = []
        self.faces_names_groups = []
        self.boxList = []
        self.CilinderList = []
        self.PontaList = []
        salome_env.room = self

        geomObj_8 = salome_env.geompy.MakeMarker(0, 0, 0, 1, 0, 0, 0, 1, 0)

        # Criação da Sala
        sk = salome_env.geompy.Sketcher2D()
        sk.addPoint(0.0000000, 0.0000000)
        sk.addSegmentAbsolute(0.0000000, dy)
        sk.addSegmentAbsolute(dx, dy)
        sk.addSegmentAbsolute(dx, 0.0000000)
        sk.close()

        Sketch_1_1 = sk.wire(geomObj_8)
        F4 = salome_env.geompy.MakeFaceWires([Sketch_1_1], 1)
        self.object = salome_env.geompy.MakePrismVecH(F4, salome_env.OZ, dz)

        if name is not None:
            salome_env.geompy.addToStudy(self.object, name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()

    def add_box_volume(self, x=1.5, z=1.5, theta=0, R_Tubo=0.1, R_Vol=0.33,
                    H_Tubo=0.92, H_Vol=0.9, Filete=0.35, name='Box', person=None):

            if person is not None:
                x = person.x
                z = person.z
                theta = person.theta

            geompy = geomBuilder.New()
            theta += 180
            Lb = 0.66
            theta = math.radians(theta)
            x1 = 0
            z1 = 0
            x2 = 0
            z2 = Lb
            x3 = Lb
            z3 = 0
            z4 = Lb
            x4 = Lb

            x_1 = x1 * math.cos(theta) + z1 * math.sin(theta)
            z_1 = -x1 * math.sin(theta) + z1 * math.cos(theta)
            x_2 = x2 * math.cos(theta) + z2 * math.sin(theta)
            z_2 = -x2 * math.sin(theta) + z2 * math.cos(theta)
            x_3 = x3 * math.cos(theta) + z3 * math.sin(theta)
            z_3 = -x3 * math.sin(theta) + z3 * math.cos(theta)
            x_4 = x4 * math.cos(theta) + z4 * math.sin(theta)
            z_4 = -x4 * math.sin(theta) + z4 * math.cos(theta)

            O = geompy.MakeVertex(0, 0, 0)
            OX = geompy.MakeVectorDXDYDZ(1, 0, 0)
            OY = geompy.MakeVectorDXDYDZ(0, 1, 0)
            OZ = geompy.MakeVectorDXDYDZ(0, 0, 1)

            P1 = geompy.MakeVertex(0, (H_Vol + H_Tubo), 0)
            P2 = geompy.MakeVertexWithRef(P1, R_Tubo, 0, 0)
            P3 = geompy.MakeVertexWithRef(P2, 0, -(H_Tubo / 2), 0)
            P4 = geompy.MakeVertexWithRef(P1, R_Vol, -H_Tubo, 0)
            P5 = geompy.MakeVertexWithRef(P4, 0, -H_Vol, 0)

            L1 = geompy.MakeLineTwoPnt(P1, P2)
            L2 = geompy.MakeLineTwoPnt(P2, P3)
            L3 = geompy.MakeLineTwoPnt(P3, P4)
            L4 = geompy.MakeLineTwoPnt(P4, P5)

            P6 = geompy.MakeVertexWithRef(P1, 0, -(H_Vol + H_Tubo), 0)
            L5 = geompy.MakeLineTwoPnt(P1, P6)
            L6 = geompy.MakeLineTwoPnt(P6, P5)

            W1 = geompy.MakeWire([L2, L3], 1e-07)
            F1 = geompy.MakeFillet1D(W1, Filete, [])
            FC1 = geompy.MakeFaceWires([L1, L4, L5, L6, F1], 1)
            R1 = geompy.MakeRevolution(FC1, L5, 360 * math.pi / 180.0)

            Vertex_1 = geompy.MakeVertex(x_1, 0, z_1)
            Vertex_2 = geompy.MakeVertex(x_2, 0, z_2)
            Vertex_3 = geompy.MakeVertex(x_3, 0, z_3)
            Vertex_4 = geompy.MakeVertex(x_4, 0, z_4)

            Line_1 = geompy.MakeLineTwoPnt(Vertex_1, Vertex_2)
            Line_3 = geompy.MakeLineTwoPnt(Vertex_3, Vertex_4)
            Line_5 = geompy.MakeLineTwoPnt(Vertex_2, Vertex_4)
            Line_2 = geompy.MakeLineTwoPnt(Vertex_1, Vertex_3)

            Face_1 = geompy.MakeFaceWires([Line_1, Line_3, Line_5, Line_2], 1)
            Extrusion_1 = geompy.MakePrismVecH(Face_1, OY, H_Vol)
            geompy.TranslateDXDYDZ(Extrusion_1, -x_2 / 2, 0, -z_2 / 2)

            Fuse_1 = geompy.MakeFuseList([R1, Extrusion_1], True, True)
            geompy.TranslateDXDYDZ(Fuse_1, x, 0, z)
            geompy.addToStudy(Fuse_1, name)
            self.boxList.append(Fuse_1)
            if salome.sg.hasDesktop():
                salome.sg.updateObjBrowser()


    def add_box_cilinder(self, x=1.5, z=1.5, R_Tubo=0.1, R_Vol=0.33,
                    H_Tubo=0.92, H_Vol=0.9, Filete=0.35, name='Box', person=None):

            if person is not None:
                x = person.x
                z = person.z
                theta = person.theta

            geompy = geomBuilder.New()

            O = geompy.MakeVertex(0, 0, 0)
            OX = geompy.MakeVectorDXDYDZ(1, 0, 0)
            OY = geompy.MakeVectorDXDYDZ(0, 1, 0)
            OZ = geompy.MakeVectorDXDYDZ(0, 0, 1)

            P1 = geompy.MakeVertex(0, (H_Tubo + H_Vol), 0)
            P2 = geompy.MakeVertexWithRef(P1, R_Tubo, 0, 0)
            P3 = geompy.MakeVertexWithRef(P2, 0, -(H_Vol / 2), 0)
            P4 = geompy.MakeVertexWithRef(P1, R_Vol, -H_Vol, 0)
            P5 = geompy.MakeVertexWithRef(P4, 0, -H_Tubo, 0)

            L1 = geompy.MakeLineTwoPnt(P1, P2)
            L2 = geompy.MakeLineTwoPnt(P2, P3)
            L3 = geompy.MakeLineTwoPnt(P3, P4)
            L4 = geompy.MakeLineTwoPnt(P4, P5)

            P6 = geompy.MakeVertexWithRef(P1, 0, -(H_Tubo + H_Vol), 0)
            L5 = geompy.MakeLineTwoPnt(P1, P6)
            L6 = geompy.MakeLineTwoPnt(P6, P5)

            W1 = geompy.MakeWire([L2, L3], 1e-07)
            F1 = geompy.MakeFillet1D(W1, Filete, [])
            FC1 = geompy.MakeFaceWires([L1, L4, L5, L6, F1], 1)
            R1 = geompy.MakeRevolution(FC1, L5, 360 * math.pi / 180.0)

            geompy.TranslateDXDYDZ(R1, x, 0, z)
            geompy.addToStudy(R1, name)
            self.boxList.append(R1)

            if salome.sg.hasDesktop():
                salome.sg.updateObjBrowser()

    def add_cilinder(self, salome_env, x=1.5, z=1.5, R_Tubo=0.05, R_Ponta=0.075,
                     H_Tubo=1.2, H_Ponta=0.085, name='Box', dip=None):
        geompy = self.salome_env.geompy

        self.salome_env = salome_env
        if salome_env.room is None:
            raise RuntimeError("Nenhuma Room foi criada.")
        self.room = salome_env.room

        if dip is not None:
            x = dip.x
            z = dip.z
            H_Tubo = dip.y
            if name == 'Box':
                name = dip.name

        O = geompy.MakeVertex(0, 0, 0)
        OX = geompy.MakeVectorDXDYDZ(1, 0, 0)
        OY = geompy.MakeVectorDXDYDZ(0, 1, 0)
        OZ = geompy.MakeVectorDXDYDZ(0, 0, 1)

        Cylinder_1 = geompy.MakeCylinder(O, OY, R_Tubo, H_Tubo)
        Cylinder_2 = geompy.MakeCylinder(O, OY, R_Ponta, H_Ponta)

        geompy.TranslateDXDYDZ(Cylinder_1, x, self.room.H - H_Tubo, z)
        geompy.TranslateDXDYDZ(
            Cylinder_2, x, self.room.H - H_Tubo - H_Ponta, z
        )
        geompy.addToStudy(Cylinder_1, name)
        geompy.addToStudy(Cylinder_2, name + "_ponta")

        self.CilinderList.append(Cylinder_1)
        self.PontaList.append(Cylinder_2)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()

    def add(self, obj_list):
            sal_obj_list = []
            for obj in obj_list:
                sal_obj_list.append(obj.object)

            self.obj_list = self.obj_list + obj_list

            self.object = self.salome_env.geompy.MakeCutList(
                self.object, sal_obj_list, True
            )
            self.n += 1
            self.salome_env.geompy.addToStudy(self.object, self.name + str(self.n))

            if salome.sg.hasDesktop():
                salome.sg.updateObjBrowser()

    def create_faces_groups(self, group_list=None, group_name=None):
        # Extrair as faces de RoomCUT e DIP
        faces_room = self.salome_env.geompy.ExtractShapes(
            self.object, self.salome_env.geompy.ShapeType["FACE"], True
        )

        # Tolerância para considerar as faces próximas
        tolerance = 1e-6  # Ajuste conforme necessário
        face_wall_ids = []
        for face_room in faces_room:
            face_wall_ids.append(
                self.salome_env.geompy.GetSubShapeID(self.object, face_room)
            )

        for obj in self.obj_list:
            face_ids = []
            faces_obj = self.salome_env.geompy.ExtractShapes(
                obj.object, self.salome_env.geompy.ShapeType["FACE"], True
            )

            # Criar um grupo para armazenar as faces correspondentes
            group_faces = self.salome_env.geompy.CreateGroup(
                self.object, self.salome_env.geompy.ShapeType["FACE"]
            )

            self.faces_groups.append(group_faces)

            if isinstance(obj, Dip):
                self.faces_names_groups.append("dip")
            elif isinstance(obj, Table):
                self.faces_names_groups.append("table")
            elif isinstance(obj, Person_seated):
                self.faces_names_groups.append("person")

            # Iterar sobre as faces e verificar proximidade e área
            dip_y_max = 0
            dip_face_max = None

            for face_obj in faces_obj:
                for face_room in faces_room:
                    if isinstance(obj, Dip):  # INLET: Busca a face do inlet
                        center = self.salome_env.geompy.MakeCDG(face_room)
                        coords = self.salome_env.geompy.PointCoordinates(center)
                        
                        cond_x = abs(coords[0] - obj.x) < tolerance
                        cond_z = abs(coords[2] - obj.z) < tolerance
                        
                        if cond_x and cond_z:
                            if coords[1] > dip_y_max:
                                dip_y_max = coords[1]
                                dip_face_max = face_room

                    distance = self.salome_env.geompy.MinDistance(
                        face_obj, face_room
                    )
                    if distance < tolerance:
                        # Calcular propriedades básicas da face
                        properties = self.salome_env.geompy.BasicProperties(
                            face_room
                        )

                        # Garantir que a área está disponível
                        if len(properties) >= 2:
                            area = properties[1]  # Segundo elemento é a área
                            if area < self.area:  # Filtrar por área
                                # Obter o ID da face em RoomCUT
                                face_id = self.salome_env.geompy.GetSubShapeID(
                                    self.object, face_room
                                )
                                # Adicionar a face ao grupo usando o ID
                                self.salome_env.geompy.AddObject(
                                    group_faces, face_id
                                )
                                face_ids.append(face_id)
                                face_wall_ids = list(
                                    set(face_wall_ids) - set([face_id])
                                )

            if isinstance(obj, Dip):  # INLET: Busca a face do inlet
                face_inlet_id = self.salome_env.geompy.GetSubShapeID(
                    self.object, dip_face_max
                )
                group_inlet = self.salome_env.geompy.CreateGroup(
                    self.object, self.salome_env.geompy.ShapeType["FACE"]
                )

                self.faces_groups.append(group_inlet)
                self.faces_names_groups.append("inlet")

                self.salome_env.geompy.AddObject(group_inlet, face_inlet_id)
                self.salome_env.geompy.addToStudyInFather(
                    self.object, group_inlet, "inlet_" + obj.name
                )
                self.inlet_faces.append(face_inlet_id)
                
                face_wall_ids = list(set(face_wall_ids) - set([face_inlet_id]))
                face_ids = list(set(face_ids) - set([face_inlet_id]))
                self.salome_env.geompy.RemoveObject(group_faces, face_inlet_id)

            face_ids.sort()
            self.salome_env.geompy.addToStudyInFather(
                self.object, group_faces, "obj_" + obj.name
            )
            obj.faces = face_ids

        face_ids = []

        # Criar um grupo para armazenar as faces correspondentes
        group_outlet = self.salome_env.geompy.CreateGroup(
            self.object, self.salome_env.geompy.ShapeType["FACE"]
        )
        self.faces_groups.append(group_outlet)
        self.faces_names_groups.append("outlet")

        # Iterar sobre as faces e verificar proximidade e área
        for face_room in faces_room:
            center = self.salome_env.geompy.MakeCDG(face_room)
            coords = self.salome_env.geompy.PointCoordinates(center)
            properties = self.salome_env.geompy.BasicProperties(face_room)

            # Verificação de outlet (topo/base e área reduzida)
            is_top_bottom = (abs(coords[1] - self.H) < tolerance or 
                             abs(coords[1]) < tolerance)
            
            if is_top_bottom and properties[1] < self.area:
                face_id = self.salome_env.geompy.GetSubShapeID(
                    self.object, face_room
                )

                if face_id not in self.inlet_faces:
                    self.salome_env.geompy.AddObject(group_outlet, face_id)
                    face_ids.append(face_id)

        self.salome_env.geompy.addToStudyInFather(
            self.object, group_outlet, "outlet_" + self.name
        )
        self.outlet_faces = face_ids
        face_wall_ids = list(set(face_wall_ids) - set(face_ids))
        face_wall_ids.sort()
        self.wall_faces = face_wall_ids

        # Criar um grupo para as paredes (wall)
        group_wall = self.salome_env.geompy.CreateGroup(
            self.object, self.salome_env.geompy.ShapeType["FACE"]
        )

        self.faces_groups.append(group_wall)
        self.faces_names_groups.append("wall")

        for face_id in face_wall_ids:
            self.salome_env.geompy.AddObject(group_wall, face_id)

        self.salome_env.geompy.addToStudyInFather(
            self.object, group_wall, "wall_" + self.name
        )

    def insert_ceiling_opening(self, x=1, z=1, d=0.025):
            
            center = self.salome_env.geompy.MakeVertex(x, self.H, z)
            circle = self.salome_env.geompy.MakeCircle(center, self.salome_env.OY, d)
            face = self.salome_env.geompy.MakeFaceWires([circle], 1)
            self.salome_env.geompy.addToStudy(face, 'opening')

            self.object = self.salome_env.geompy.MakePartitionNonSelfIntersectedShape(
                [self.object], [face], [], [],
                self.salome_env.geompy.ShapeType["SOLID"], 0, [], 1, True
            )
            self.n += 1
            self.salome_env.geompy.addToStudy(self.object, self.name + str(self.n))

            salome.sg.updateObjBrowser()

    def insert_floor_opening(self, x=1, z=1, d=0.025):

            center = self.salome_env.geompy.MakeVertex(x, 0, z)
            circle = self.salome_env.geompy.MakeCircle(center, self.salome_env.OY, d)
            face = self.salome_env.geompy.MakeFaceWires([circle], 1)
            self.salome_env.geompy.addToStudy(face, 'opening')

            self.object = self.salome_env.geompy.MakePartitionNonSelfIntersectedShape(
                [self.object], [face], [], [],
                self.salome_env.geompy.ShapeType["SOLID"], 0, [], 1, True
            )
            self.n += 1
            self.salome_env.geompy.addToStudy(self.object, self.name + str(self.n))

            salome.sg.updateObjBrowser()

    def create_mesh(self, mesh=None, K_mesh=1, export=False, caminho=''):
        if mesh is None:
            mesh = Mesh_configuration()

        smesh = smeshBuilder.New()
        inicio = time.time()

        Mesh_1 = smesh.Mesh(self.object, 'Mesh_1')
        NETGEN_1D_2D = Mesh_1.Triangle(algo=smeshBuilder.NETGEN_1D2D)
        NETGEN_2D_Parameters_1 = NETGEN_1D_2D.Parameters()

        # Parâmetros Gerais 2D (faces)
        NETGEN_2D_Parameters_1.SetMaxSize(mesh.m2DMaxSize)
        NETGEN_2D_Parameters_1.SetMinSize(mesh.m2DMinSize)
        NETGEN_2D_Parameters_1.SetSecondOrder(0)
        NETGEN_2D_Parameters_1.SetOptimize(1)
        NETGEN_2D_Parameters_1.SetFineness(3)
        NETGEN_2D_Parameters_1.SetChordalError(-1)
        NETGEN_2D_Parameters_1.SetChordalErrorEnabled(0)
        NETGEN_2D_Parameters_1.SetUseSurfaceCurvature(1)
        NETGEN_2D_Parameters_1.SetFuseEdges(1)
        NETGEN_2D_Parameters_1.SetUseDelauney(0)
        NETGEN_2D_Parameters_1.SetQuadAllowed(0)
        NETGEN_2D_Parameters_1.SetWorstElemMeasure(230)
        NETGEN_2D_Parameters_1.SetCheckChartBoundary(224)

        # Parâmetros Gerais 3D (volumes)
        NETGEN_3D = Mesh_1.Tetrahedron()
        NETGEN_3D_Parameters_1 = NETGEN_3D.Parameters()
        NETGEN_3D_Parameters_1.SetMaxSize(0.075 * K_mesh)
        NETGEN_3D_Parameters_1.SetMinSize(0.001)
        NETGEN_3D_Parameters_1.SetOptimize(1)
        NETGEN_3D_Parameters_1.SetFineness(3)  # 2 - Coarse, 3 - Fine
        NETGEN_3D_Parameters_1.SetCheckOverlapping(0)
        NETGEN_3D_Parameters_1.SetElemSizeWeight(1.51004e-311)
        NETGEN_3D_Parameters_1.SetCheckChartBoundary(224)

        for box in self.boxList:
            NETGEN_3D_Parameters_1.SetLocalSizeOnShape(box, 0.02 * K_mesh)
        for cilinder in self.CilinderList:
            NETGEN_3D_Parameters_1.SetLocalSizeOnShape(cilinder, 0.01 * K_mesh)
        for ponta in self.PontaList:
            NETGEN_3D_Parameters_1.SetLocalSizeOnShape(ponta, 0.0065 * K_mesh)

        # Parâmetros: Objects
        Viscous_Layers = []
        Groups = []
        Names = []

        for i in range(len(self.faces_groups)):
            f_grp = self.faces_groups[i]
            f_name = self.faces_names_groups[i]

            if f_name == 'dip':
                NETGEN_2D_Parameters_1.SetLocalSizeOnShape(f_grp, 0.005)
                v_layer = NETGEN_3D.ViscousLayers(
                    0.0025, 5, 1.2, f_grp, 0, smeshBuilder.SURF_OFFSET_SMOOTH
                )
                Viscous_Layers.append(v_layer)
                Groups.append(Mesh_1.GroupOnGeom(
                    f_grp, 'dip' + str(len(Groups)), SMESH.FACE)
                )
                Names.append('dip' + str(len(Groups)))

            elif f_name == 'person':
                NETGEN_2D_Parameters_1.SetLocalSizeOnShape(f_grp, 0.02)
                v_layer = NETGEN_3D.ViscousLayers(
                    0.01, 5, 1.2, f_grp, 0, smeshBuilder.SURF_OFFSET_SMOOTH
                )
                Viscous_Layers.append(v_layer)
                Groups.append(Mesh_1.GroupOnGeom(
                    f_grp, 'person' + str(len(Groups)), SMESH.FACE)
                )
                Names.append('person' + str(len(Groups)))

            elif f_name == 'wall':
                NETGEN_2D_Parameters_1.SetLocalSizeOnShape(f_grp, 0.050)
                v_layer = NETGEN_3D.ViscousLayers(
                    0.030, 5, 1.2, f_grp, 0, smeshBuilder.SURF_OFFSET_SMOOTH
                )
                Viscous_Layers.append(v_layer)
                Groups.append(Mesh_1.GroupOnGeom(
                    f_grp, 'wall' + str(len(Groups)), SMESH.FACE)
                )
                Names.append('wall' + str(len(Groups)))

            elif f_name == 'table':
                NETGEN_2D_Parameters_1.SetLocalSizeOnShape(f_grp, 0.02)
                v_layer = NETGEN_3D.ViscousLayers(
                    0.01, 5, 1.2, f_grp, 0, smeshBuilder.SURF_OFFSET_SMOOTH
                )
                Viscous_Layers.append(v_layer)
                Groups.append(Mesh_1.GroupOnGeom(
                    f_grp, 'table' + str(len(Groups)), SMESH.FACE)
                )
                Names.append('table' + str(len(Groups)))

            elif f_name == 'outlet':
                NETGEN_2D_Parameters_1.SetLocalSizeOnShape(f_grp, 0.03)
                Groups.append(Mesh_1.GroupOnGeom(
                    f_grp, 'outlet' + str(len(Groups)), SMESH.FACE)
                )
                Names.append('outlet' + str(len(Groups)))

            elif f_name == 'inlet':
                NETGEN_2D_Parameters_1.SetLocalSizeOnShape(f_grp, 0.03)
                Groups.append(Mesh_1.GroupOnGeom(
                    f_grp, 'inlet' + str(len(Groups)), SMESH.FACE)
                )
                Names.append('inlet' + str(len(Groups)))

        isDone = Mesh_1.Compute()

        smesh.SetName(NETGEN_1D_2D.GetAlgorithm(), 'NETGEN 1D-2D')
        smesh.SetName(NETGEN_3D.GetAlgorithm(), 'NETGEN 3D')
        smesh.SetName(NETGEN_3D_Parameters_1, 'NETGEN 3D Parameters_1')
        smesh.SetName(NETGEN_2D_Parameters_1, 'NETGEN 2D Parameters_1')

        for i, viscous in enumerate(Viscous_Layers, 1):
            smesh.SetName(viscous, 'Viscous Layers_' + str(i))

        for group, name in zip(Groups, Names):
            smesh.SetName(group, name)

        smesh.SetName(Mesh_1.GetMesh(), 'Mesh_1')
        fim = time.time()
        print(f"Tempo de execução da Malha: {fim - inicio:.4f} segundos")

        if export == True:
            print('Exportando a malha para: ' + caminho)
            Mesh_1.ExportUNV(caminho, 0)


class Mesh_configuration:

    def __init__(self):
        self.m2DMaxSize = 0.2
        self.m2DMinSize = 0.02

    def set2Dsizes(self, maxSize, minSize):
        self.m2DMaxSize = maxSize
        self.m2DMinSize = minSize


class Person:

    def __init__(self, salome_env, name='Person'):

        self.salome_env = salome_env
        self.name = name
        self.faces = None

    def seated(self, h=1.700, thickness=0.200, width=0.225,
                 fillet_radius=0.030, x=1, z=1.5, theta=0):
        
        self.x = x
        self.z = z
        self.theta = theta

        theta = math.radians(theta)
        d1 = thickness
        cabeca = h * (1.25 / 8)
        tronco = h * (2.25 / 8)
        tibia = h * (2.5 / 8)
        femur = h * (2 / 8)
        d5 = tibia
        d6 = femur
        d7 = tronco
        d4 = d7 + d1
        d3 = d6
        d2 = d5 - d1
        d8 = 0.15 * cabeca
        d9 = 0.85 * cabeca

        geomObj_10 = self.salome_env.geompy.MakeMarker(0, 0, 0, 1, 0, 0, 0, 1, 0)
        geomObj_11 = self.salome_env.geompy.MakeMarker(0, 0, 0, 1, 0, 0, 0, 1, 0)

        # Criação do manequim
        sk = self.salome_env.geompy.Sketcher2D()
        sk.addPoint(0.0000000, 0.0000000)
        sk.addSegmentAbsolute(0.0000000, 3.000)
        sk.addSegmentAbsolute(3.000, 3.000)
        sk.addSegmentAbsolute(3.000, 0.0000000)
        sk.close()

        Sketch_1_2 = sk.wire(geomObj_11)
        x37, z37 = -(d6 + d1 / 2), 0
        x38, z38 = d1, 0
        x40, z40 = d3, 0
        x43, z43 = d6, 0
        x86, z86 = d6, 0.2

        x_37 = x37 * math.cos(theta) + z37 * math.sin(theta)
        z_37 = -x37 * math.sin(theta) + z37 * math.cos(theta)
        x_38 = x38 * math.cos(theta) + z38 * math.sin(theta)
        z_38 = -x38 * math.sin(theta) + z38 * math.cos(theta)
        x_40 = x40 * math.cos(theta) + z40 * math.sin(theta)
        z_40 = -x40 * math.sin(theta) + z40 * math.cos(theta)
        x_43 = x43 * math.cos(theta) + z43 * math.sin(theta)
        z_43 = -x43 * math.sin(theta) + z43 * math.cos(theta)

        P37 = self.salome_env.geompy.MakeVertex(x_37, 0, z_37)
        P38 = self.salome_env.geompy.MakeVertexWithRef(P37, x_38, 0, z_38)
        P39 = self.salome_env.geompy.MakeVertexWithRef(P38, 0, d2, 0)
        P40 = self.salome_env.geompy.MakeVertexWithRef(P39, x_40, 0, z_40)
        P41 = self.salome_env.geompy.MakeVertexWithRef(P40, 0, d4, 0)
        P42 = self.salome_env.geompy.MakeVertexWithRef(P37, 0, d5, 0)
        P43 = self.salome_env.geompy.MakeVertexWithRef(P42, x_43, 0, z_43)
        P44 = self.salome_env.geompy.MakeVertexWithRef(P43, 0, d7, 0)

        L15 = self.salome_env.geompy.MakeLineTwoPnt(P37, P38)
        L16 = self.salome_env.geompy.MakeLineTwoPnt(P38, P39)
        L17 = self.salome_env.geompy.MakeLineTwoPnt(P39, P40)
        L18 = self.salome_env.geompy.MakeLineTwoPnt(P40, P41)
        L19 = self.salome_env.geompy.MakeLineTwoPnt(P41, P44)
        L20 = self.salome_env.geompy.MakeLineTwoPnt(P44, P43)
        L21 = self.salome_env.geompy.MakeLineTwoPnt(P43, P42)
        L22 = self.salome_env.geompy.MakeLineTwoPnt(P42, P37)

        x45, z45 = -(d1 / 4), 0
        x46, z46 = -(d1 / 2), 0
        x48, z48 = d1 / 4, 0

        x_45 = x45 * math.cos(theta) + z45 * math.sin(theta)
        z_45 = -x45 * math.sin(theta) + z45 * math.cos(theta)
        x_46 = x46 * math.cos(theta) + z46 * math.sin(theta)
        z_46 = -x46 * math.sin(theta) + z46 * math.cos(theta)
        x_48 = x48 * math.cos(theta) + z48 * math.sin(theta)
        z_48 = -x48 * math.sin(theta) + z48 * math.cos(theta)
        x_86 = x86 * math.cos(theta) + z86 * math.sin(theta)
        z_86 = -x86 * math.sin(theta) + z86 * math.cos(theta)

        P45 = self.salome_env.geompy.MakeVertexWithRef(P41, x_45, 0, z_45)
        P46 = self.salome_env.geompy.MakeVertexWithRef(P41, x_46, 0, z_46)
        P47 = self.salome_env.geompy.MakeVertexWithRef(P46, 0, (d8 + (d9 / 2)), 0)
        P48 = self.salome_env.geompy.MakeVertexWithRef(P44, x_48, 0, z_48)
        P49 = self.salome_env.geompy.MakeVertexWithRef(P45, 0, ((d8 + (d9 / 2)) - 0.010), 0)
        P50 = self.salome_env.geompy.MakeVertexWithRef(P48, 0, ((d8 + (d9 / 2)) - 0.010), 0)
        P55 = self.salome_env.geompy.MakeVertexWithRef(P42, x_86, 0, z_86)

        L29 = self.salome_env.geompy.MakeLineTwoPnt(P43, P55)
        C7 = self.salome_env.geompy.MakeCircle(P47, L29, d9 / 2)
        L23 = self.salome_env.geompy.MakeLineTwoPnt(P41, P45)
        L24 = self.salome_env.geompy.MakeLineTwoPnt(P45, P49)
        L25 = self.salome_env.geompy.MakeLineTwoPnt(P49, P50)
        L26 = self.salome_env.geompy.MakeLineTwoPnt(P50, P48)
        L27 = self.salome_env.geompy.MakeLineTwoPnt(P48, P44)

        W1 = self.salome_env.geompy.MakeWire([L23, L24], 1e-07)
        W2 = self.salome_env.geompy.MakeWire([L26, L27], 1e-07)
        FIL1 = self.salome_env.geompy.MakeFillet1D(W1, d1 / 8, [])
        FIL2 = self.salome_env.geompy.MakeFillet1D(W2, d1 / 8, [])

        P51 = self.salome_env.geompy.MakeVertexWithRef(P47, 0, cabeca, 0)
        L28 = self.salome_env.geompy.MakeLineTwoPnt(P46, P51)
        F8 = self.salome_env.geompy.MakeFaceWires([C7], 1)
        F9 = self.salome_env.geompy.MakeFaceWires([L19, L25, FIL1, FIL2], 1)

        PARTITION3 = self.salome_env.geompy.MakePartitionNonSelfIntersectedShape(
                [F8, F9], [L28], [], [], self.salome_env.geompy.ShapeType["FACE"],
                0, [], 1, True
            )

        [F10] = self.salome_env.geompy.SubShapes(PARTITION3, [2])
        [F11] = self.salome_env.geompy.SubShapes(PARTITION3, [21])
        [F12] = self.salome_env.geompy.SubShapes(PARTITION3, [29])

        FUSE2 = self.salome_env.geompy.MakeFuseList([F10, F11, F12], True, True)
        REVOLUTION2 = self.salome_env.geompy.MakeRevolution(
                FUSE2, L28, 360 * math.pi / 180.0
            )
        F14 = self.salome_env.geompy.MakeFaceWires(
                [L15, L16, L17, L18, L19, L20, L21, L22], 1
            )
        EXTRUSION3 = self.salome_env.geompy.MakePrismVecH2Ways(F14, L29, width)
        FUSE3 = self.salome_env.geompy.MakeFuseList([REVOLUTION2, EXTRUSION3], True, True)

        edges_to_fillet = [
                15, 18, 19, 22, 25, 26, 29, 31, 33, 35,
                37, 40, 42, 44, 46, 48, 51, 54, 57, 60
            ]
        FIL3 = self.salome_env.geompy.MakeFillet(
                FUSE3, fillet_radius, self.salome_env.geompy.ShapeType["EDGE"],
                edges_to_fillet
            )

        self.object = self.salome_env.geompy.MakeTranslation(FIL3, x, 0, z)
        self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()

        return self

    def standing(self, x=1, z=1.5, theta=0):
            
        self.x = x
        self.z = z
        self.theta = theta

        P1 = self.salome_env.geompy.MakeVertex(0, 0, 0)
        P2 = self.salome_env.geompy.MakeVertexWithRef(P1, 0.20, 0, 0)
        P3 = self.salome_env.geompy.MakeVertexWithRef(P1, 0, 1.40, 0)
        P4 = self.salome_env.geompy.MakeVertexWithRef(P2, 0, 1.40, 0)
        L1 = self.salome_env.geompy.MakeLineTwoPnt(P1, P2)
        L2 = self.salome_env.geompy.MakeLineTwoPnt(P2, P4)
        L3 = self.salome_env.geompy.MakeLineTwoPnt(P4, P3)
        L4 = self.salome_env.geompy.MakeLineTwoPnt(P3, P1)
        P5 = self.salome_env.geompy.MakeVertexWithRef(P3, 0.055, 0, 0)
        P6 = self.salome_env.geompy.MakeVertexWithRef(P4, -0.055, 0, 0)
        P7 = self.salome_env.geompy.MakeVertexWithRef(P4, -0.10, 0, 0)
        P9 = self.salome_env.geompy.MakeVertexWithRef(P5, 0, 0.142, 0)
        P10 = self.salome_env.geompy.MakeVertexWithRef(P6, 0, 0.142, 0)
        L5 = self.salome_env.geompy.MakeLineTwoPnt(P3, P5)
        L6 = self.salome_env.geompy.MakeLineTwoPnt(P5, P9)
        L7 = self.salome_env.geompy.MakeLineTwoPnt(P9, P10)
        L8 = self.salome_env.geompy.MakeLineTwoPnt(P10, P6)
        L9 = self.salome_env.geompy.MakeLineTwoPnt(P6, P4)
        P8 = self.salome_env.geompy.MakeVertexWithRef(P7, 0, 0.162, 0)
        C1 = self.salome_env.geompy.MakeCircle(P8, None, 0.115)
        W1 = self.salome_env.geompy.MakeWire([L5, L6], 1e-07)
        W2 = self.salome_env.geompy.MakeWire([L8, L9], 1e-07)
        FIL1 = self.salome_env.geompy.MakeFillet1D(W1, 0.03, [])
        FIL2 = self.salome_env.geompy.MakeFillet1D(W2, 0.03, [])
        P11 = self.salome_env.geompy.MakeVertexWithRef(P7, 0, 2.00, 0)
        L10 = self.salome_env.geompy.MakeLineTwoPnt(P11, P7)
        P11_1 = self.salome_env.geompy.MakeVertexWithRef(P1, 0, 0, 0.10)
        L11 = self.salome_env.geompy.MakeLineTwoPnt(P1, P11_1)
        F1 = self.salome_env.geompy.MakeFaceWires([C1], 1)
        F2 = self.salome_env.geompy.MakeFaceWires([L3, L7, FIL1, FIL2], 1)
        PARTITION1 = self.salome_env.geompy.MakePartitionNonSelfIntersectedShape([F1, F2], [L10], [], [], self.salome_env.geompy.ShapeType["FACE"], 0, [], 1, True)
        [F3,F4,F5] = self.salome_env.geompy.SubShapes(PARTITION1, [2, 21, 29])
        FUSE1 = self.salome_env.geompy.MakeFuseList([F3, F4, F5], True, True)
        REVOLUTION1 = self.salome_env.geompy.MakeRevolution(FUSE1, L10, -360*math.pi/180.0)
        F6 = self.salome_env.geompy.MakeFaceWires([L1, L2, L3, L4], 1)
        EXTRUSION1 = self.salome_env.geompy.MakePrismVecH2Ways(F6, L11, 0.30)
        FUSE2 = self.salome_env.geompy.MakeFuseList([REVOLUTION1, EXTRUSION1], True, True)
        Fillet_1 = self.salome_env.geompy.MakeFillet(FUSE2, 0.03, self.salome_env.geompy.ShapeType["EDGE"], [15, 18, 19, 22, 25, 26, 29, 32])
        self.salome_env.geompy.Rotate(Fillet_1, L4, theta*math.pi/180.0)

        self.object = self.salome_env.geompy.MakeTranslation(Fillet_1, x-0.10, 0, z)
        self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()

        return self

class Dip:

    def __init__(self, salome_env, d=0.05, x=1, y=1.2, z=1.5, name='DIP'):

        self.salome_env = salome_env
        self.room = salome_env.room
        self.name = name
        self.x = x
        self.y = y
        self.z = z
        self.d = d
        self.faces = None
        self.inlet_face = None

        # --- GEOMETRIA COMUM ---
        geomObj_1 = self.salome_env.geompy.MakeMarker(0, 0, 0, 1, 0, 0, 0, 1, 0)

        sk = self.salome_env.geompy.Sketcher2D()
        sk.addPoint(0.0000000, 0.0000000)
        sk.addSegmentAbsolute(0.0000000, 3.000)
        sk.addSegmentAbsolute(3.000, 3.000)
        sk.addSegmentAbsolute(3.000, 0.0000000)
        sk.close()

        Sketch_1 = sk.wire(geomObj_1)
        
        # Variáveis locais (usadas apenas aqui para construir a base)
        P1 = self.salome_env.geompy.MakeVertex(0, 0.070, 0)
        P2 = self.salome_env.geompy.MakeVertexWithRef(P1, 0, -0.005, 0)
        P3 = self.salome_env.geompy.MakeVertexWithRef(P1, 0, -0.070, 0)
        P4 = self.salome_env.geompy.MakeVertexWithRef(P3, 3.000, 0, 0)
        P5 = self.salome_env.geompy.MakeVertexWithRef(P2, 3.000, 0, 0)
        P6 = self.salome_env.geompy.MakeVertexWithRef(P1, 3.000, 0, 0)

        L1 = self.salome_env.geompy.MakeLineTwoPnt(P1, P6)
        self.L2 = self.salome_env.geompy.MakeLineTwoPnt(P2, P5)
        self.L3 = self.salome_env.geompy.MakeLineTwoPnt(P3, P4)

        P8 = self.salome_env.geompy.MakeVertexWithRef(P1, 0, -3.000, 0)
        
        # 2. ATENÇÃO: Salvamos L4 e P9 com "self." porque precisaremos deles no type_00!
        self.L4 = self.salome_env.geompy.MakeLineTwoPnt(P1, P8)
        self.P9 = self.salome_env.geompy.MakeVertexOnLinesIntersection(L1, self.L4)


    def type_00(self):

        P13 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.033, 0, 0)
        P14 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.035, 0, 0)
        P21 = self.salome_env.geompy.MakeVertexWithRef(P13, (self.d - 0.033), 0, 0)
        P22 = self.salome_env.geompy.MakeVertexWithRef(P14, (self.d - 0.033), 0, 0)
        P29 = self.salome_env.geompy.MakeVertexWithRef(P21, 0, self.y, 0)
        P30 = self.salome_env.geompy.MakeVertexWithRef(P22, 0, self.y, 0)

        L8 = self.salome_env.geompy.MakeLineTwoPnt(P22, P30)
        L9 = self.salome_env.geompy.MakeLineTwoPnt(P30, P29)
        L10 = self.salome_env.geompy.MakeLineTwoPnt(P29, P21)
        L11 = self.salome_env.geompy.MakeLineTwoPnt(P21, P22)

        F3 = self.salome_env.geompy.MakeFaceWires([L8, L9, L10, L11], 1)
        
        # Acessamos self.L4 aqui
        REVOLUTION1_2 = self.salome_env.geompy.MakeRevolution(
            F3, self.L4, 360 * math.pi / 180.0
        )
        
        # Acessamos self.x, self.y, self.z, etc.
        self.object = self.salome_env.geompy.MakeTranslation(
            REVOLUTION1_2, self.x, self.room.H - 0.07 - self.y, self.z
        )
        
        if self.name is not None:
            self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()
            
        return self

    def type_01(self):
        
        P10 = self.salome_env.geompy.MakeVertexOnLinesIntersection(self.L2, self.L4)
        P11 = self.salome_env.geompy.MakeVertexOnLinesIntersection(self.L3, self.L4)
        P12 = self.salome_env.geompy.MakeVertexWithRef(P11, 0, 0.035, 0)
        E1 = self.salome_env.geompy.MakeEllipse(P12, None, 0.035, 0.014, self.L4)

        P13 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.033, 0, 0)
        P14 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.035, 0, 0)
        P15 = self.salome_env.geompy.MakeVertexWithRef(P10, 0.033, 0, 0)
        P16 = self.salome_env.geompy.MakeVertexWithRef(P10, 0.035, 0, 0)
        P17 = self.salome_env.geompy.MakeVertexWithRef(P15, 0.140, 0, 0)
        P18 = self.salome_env.geompy.MakeVertexWithRef(P16, 0.140, 0, 0)

        C1 = self.salome_env.geompy.MakeCircle(P17, None, 0.140)
        C2 = self.salome_env.geompy.MakeCircle(P18, None, 0.140)
        P19 = self.salome_env.geompy.MakeVertexOnLinesIntersection(C1, self.L3)
        P20 = self.salome_env.geompy.MakeVertexOnLinesIntersection(C2, self.L3)

        P19_vertex_3 = self.salome_env.geompy.GetSubShape(P19, [3])
        A1 = self.salome_env.geompy.MakeArc(P13, P15, P19_vertex_3)
        P20_vertex_3 = self.salome_env.geompy.GetSubShape(P20, [3])
        A2 = self.salome_env.geompy.MakeArc(P14, P16, P20_vertex_3)

        P21 = self.salome_env.geompy.MakeVertexWithRef(P13, (self.d - 0.033), 0, 0)
        P22 = self.salome_env.geompy.MakeVertexWithRef(P14, (self.d - 0.033), 0, 0)
        P23 = self.salome_env.geompy.MakeVertexWithRef(P21, 0.150, 0, 0)
        P24 = self.salome_env.geompy.MakeVertexWithRef(P22, 0.150, 0, 0)

        C3 = self.salome_env.geompy.MakeCircle(P23, None, 0.150)
        C4 = self.salome_env.geompy.MakeCircle(P24, None, 0.150)
        P25 = self.salome_env.geompy.MakeVertexOnLinesIntersection(C3, self.L3)
        P26 = self.salome_env.geompy.MakeVertexOnLinesIntersection(C4, self.L3)
        P27 = self.salome_env.geompy.MakeVertexWithRef(P15, (self.d - 0.033), 0, 0)
        P28 = self.salome_env.geompy.MakeVertexWithRef(P16, (self.d - 0.033), 0, 0)

        P25_vertex_3 = self.salome_env.geompy.GetSubShape(P25, [3])
        A3 = self.salome_env.geompy.MakeArc(P21, P27, P25_vertex_3)
        P26_vertex_3 = self.salome_env.geompy.GetSubShape(P26, [3])
        A4 = self.salome_env.geompy.MakeArc(P22, P28, P26_vertex_3)

        P29 = self.salome_env.geompy.MakeVertexWithRef(P21, 0, self.y, 0)
        P30 = self.salome_env.geompy.MakeVertexWithRef(P22, 0, self.y, 0)

        L5 = self.salome_env.geompy.MakeLineTwoPnt(P13, P14)
        L6 = self.salome_env.geompy.MakeLineTwoPnt(P19_vertex_3, P20_vertex_3)
        L7 = self.salome_env.geompy.MakeLineTwoPnt(P25_vertex_3, P26_vertex_3)
        L8 = self.salome_env.geompy.MakeLineTwoPnt(P22, P30)
        L9 = self.salome_env.geompy.MakeLineTwoPnt(P30, P29)
        L10 = self.salome_env.geompy.MakeLineTwoPnt(P29, P21)

        DIVISAO = self.salome_env.geompy.MakeFaceWires([E1], 1)
        F2 = self.salome_env.geompy.MakeFaceWires([A1, A2, L5, L6], 1)
        F3 = self.salome_env.geompy.MakeFaceWires([A3, A4, L7, L8, L9, L10], 1)

        PARTITION1 = self.salome_env.geompy.MakePartitionNonSelfIntersectedShape(
            [DIVISAO], [self.L4], [], [],
            self.salome_env.geompy.ShapeType["FACE"], 0, [], 1, True
        )
        [F1] = self.salome_env.geompy.SubShapes(PARTITION1, [8])

        REVOLUTION1_1 = self.salome_env.geompy.MakeRevolution(
            F2, self.L4, 360 * math.pi / 180.0
        )
        REVOLUTION1_2 = self.salome_env.geompy.MakeRevolution(
            F3, self.L4, 360 * math.pi / 180.0
        )
        REVOLUTION1_3 = self.salome_env.geompy.MakeRevolution(
            F1, self.L4, 360 * math.pi / 180.0
        )

        FUSE1 = self.salome_env.geompy.MakeFuseList(
            [REVOLUTION1_1, REVOLUTION1_2, REVOLUTION1_3], True
        )
        self.object = self.salome_env.geompy.MakeTranslation(
            FUSE1, self.x, self.room.H - 0.07 - self.y, self.z
        )
        if self.name is not None:
            self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()
            
        return self

    def type_02(self):

        PP13 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.033, 0, 0)
        P14 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.035, 0, 0)
        P21 = self.salome_env.geompy.MakeVertexWithRef(PP13, (self.d - 0.033), 0, 0)
        P22 = self.salome_env.geompy.MakeVertexWithRef(P14, (self.d - 0.033), 0, 0)
        P29 = self.salome_env.geompy.MakeVertexWithRef(P21, 0, self.y, 0)
        P30 = self.salome_env.geompy.MakeVertexWithRef(P22, 0, self.y, 0)

        LL8 = self.salome_env.geompy.MakeLineTwoPnt(P22, P30)
        LL9 = self.salome_env.geompy.MakeLineTwoPnt(P30, P29)
        LL10 = self.salome_env.geompy.MakeLineTwoPnt(P29, P21)
        LL11 = self.salome_env.geompy.MakeLineTwoPnt(P21, P22)

        FF3 = self.salome_env.geompy.MakeFaceWires([LL8, LL9, LL10, LL11], 1)
        REVOLUTION1_2 = self.salome_env.geompy.MakeRevolution(
            FF3, self.L4, 360 * math.pi / 180.0
        )
        REVOLUTION1_2 = self.salome_env.geompy.MakeTranslation(
            REVOLUTION1_2, self.x, self.room.H - 0.07 - self.y, self.z
        )

        P1 = self.salome_env.geompy.MakeVertex(0, 1, 0)
        P2 = self.salome_env.geompy.MakeVertexWithRef(P1, 0.05, 0, 0)
        P3 = self.salome_env.geompy.MakeVertexWithRef(P1, 0, -0.7, 0)
        P4 = self.salome_env.geompy.MakeVertexWithRef(P2, 0, -0.7, 0)
        P5 = self.salome_env.geompy.MakeVertexWithRef(P3, 0, -0.03845, 0)
        P6 = self.salome_env.geompy.MakeVertexWithRef(P5, 0.00522, -0.00523, 0)
        P7 = self.salome_env.geompy.MakeVertexWithRef(P5, 0.019, -0.09523, 0)
        P8 = self.salome_env.geompy.MakeVertexWithRef(P5, 0.02, -0.16523, 0)

        geomObj_1 = self.salome_env.geompy.MakeLineTwoPnt(P2, P4)
        L2 = self.salome_env.geompy.MakeLineTwoPnt(P5, P6)
        L3 = self.salome_env.geompy.MakeLineTwoPnt(P6, P7)
        L4_local = self.salome_env.geompy.MakeLineTwoPnt(P7, P8)

        P9 = self.salome_env.geompy.MakeVertexWithRef(P3, 0, -0.26155, 0)
        L5 = self.salome_env.geompy.MakeLineTwoPnt(P8, P9)
        P10 = self.salome_env.geompy.MakeVertexWithRef(P3, 0, -0.3, 0)
        P11 = self.salome_env.geompy.MakeVertexWithRef(P7, 0.018, 0, 0)
        P12 = self.salome_env.geompy.MakeVertexWithRef(P10, 0.06448999999999999, 0, 0)

        L6 = self.salome_env.geompy.MakeLineTwoPnt(P11, P12)
        P13 = self.salome_env.geompy.MakeVertexWithRef(P5, 0.02352, 0, 0)
        L7 = self.salome_env.geompy.MakeLineTwoPnt(P11, P13)
        P15 = self.salome_env.geompy.MakeVertexWithRef(P4, 0.05, -0.09868, 0)
        P16 = self.salome_env.geompy.MakeVertexWithRef(P4, 0.076, -0.3, 0)
        L9 = self.salome_env.geompy.MakeLineTwoPnt(P16, P15)
        P17 = self.salome_env.geompy.MakeVertexWithRef(P12, 0.0245, 0.10632, 0)
        L10 = self.salome_env.geompy.MakeLineTwoPnt(P13, P17)
        L11 = self.salome_env.geompy.MakeLineTwoPnt(P17, P12)

        W1 = self.salome_env.geompy.MakeWire([L2, L3], 1e-07)
        W2 = self.salome_env.geompy.MakeWire([L4_local, L5], 1e-07)
        W3 = self.salome_env.geompy.MakeWire([L10, L11], 1e-07)

        F1 = self.salome_env.geompy.MakeFillet1D(W1, 0.008, [])
        F2 = self.salome_env.geompy.MakeFillet1D(W2, 0.02, [])
        F3 = self.salome_env.geompy.MakeFillet1D(W3, 0.15, [])

        L8 = self.salome_env.geompy.MakeLineTwoPnt(P4, P15)
        geomObj_2 = self.salome_env.geompy.MakeWire([geomObj_1, L9, L8], 1e-07)
        F4 = self.salome_env.geompy.MakeFillet1D(geomObj_2, 0.25, [])

        EIXO = self.salome_env.geompy.MakeLineTwoPnt(P5, P9)
        FC1 = self.salome_env.geompy.MakeFaceWires([W1, W2, EIXO], 1)
        FC2 = self.salome_env.geompy.MakeFaceWires([L6, L7, F3], 1)

        geomObj_3 = self.salome_env.geompy.MakeRevolution(
            geomObj_2, EIXO, -180 * math.pi / 180.0
        )
        R1_2 = self.salome_env.geompy.MakeRevolution(
            FC1, EIXO, -360 * math.pi / 180.0
        )
        R1_3 = self.salome_env.geompy.MakeRevolution(
            FC2, EIXO, -360 * math.pi / 180.0
        )

        L8_vertex_2 = self.salome_env.geompy.GetSubShape(L8, [2])
        P18 = self.salome_env.geompy.MakeVertexWithRef(L8_vertex_2, -0.002, 0, 0)
        L8_1 = self.salome_env.geompy.MakeLineTwoPnt(P18, L8_vertex_2)

        W4 = self.salome_env.geompy.MakeWire([L8, L9], 1e-07)
        TR1 = self.salome_env.geompy.MakeTranslation(W4, +0.002, 0, 0)
        TR1_vertex_3 = self.salome_env.geompy.GetSubShape(TR1, [3])
        W4_vertex_3 = self.salome_env.geompy.GetSubShape(W4, [3])
        L12 = self.salome_env.geompy.MakeLineTwoPnt(TR1_vertex_3, W4_vertex_3)

        TR1_vertex_6 = self.salome_env.geompy.GetSubShape(TR1, [6])
        W4_vertex_6 = self.salome_env.geompy.GetSubShape(W4, [6])
        L13 = self.salome_env.geompy.MakeLineTwoPnt(TR1_vertex_6, W4_vertex_6)

        FC3 = self.salome_env.geompy.MakeFaceWires([W4, TR1, L12, L13], 1)
        R1_3_1 = self.salome_env.geompy.MakeRevolution(
            FC3, EIXO, -360 * math.pi / 180.0
        )

        FS1 = self.salome_env.geompy.MakeFuseList(
            [R1_3_1, R1_2, R1_3], True, True
        )
        TR2 = self.salome_env.geompy.MakeTranslation(
            FS1, self.x, self.room.H - 0.3 - self.y, self.z
        )

        FS2 = self.salome_env.geompy.MakeFuseList(
            [TR2, REVOLUTION1_2], True, True
        )
        # Mantida tradução 0,0,0 conforme lógica original
        self.object = self.salome_env.geompy.MakeTranslation(FS2, 0, 0, 0)
        if self.name is not None:
            self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()
            
        return self

    def type_03(self):

        P13 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.033, 0, 0)
        P14 = self.salome_env.geompy.MakeVertexWithRef(self.P9, 0.035, 0, 0)
        P21 = self.salome_env.geompy.MakeVertexWithRef(P13, (self.d - 0.033), 0, 0)
        P22 = self.salome_env.geompy.MakeVertexWithRef(P14, (self.d - 0.033), 0, 0)
        P29 = self.salome_env.geompy.MakeVertexWithRef(P21, 0, self.y, 0)
        P30 = self.salome_env.geompy.MakeVertexWithRef(P22, 0, self.y, 0)

        L8 = self.salome_env.geompy.MakeLineTwoPnt(P22, P30)
        L9 = self.salome_env.geompy.MakeLineTwoPnt(P30, P29)
        L10 = self.salome_env.geompy.MakeLineTwoPnt(P29, P21)
        L11 = self.salome_env.geompy.MakeLineTwoPnt(P21, P22)

        F3 = self.salome_env.geompy.MakeFaceWires([L8, L9, L10, L11], 1)
        REVOLUTION1_2 = self.salome_env.geompy.MakeRevolution(
            F3, self.L4, 360 * math.pi / 180.0
        )

        O_o = self.salome_env.geompy.MakeVertex(0, 0, 0)
        Vertex_1 = self.salome_env.geompy.MakeVertex(0.065, 0, 0)
        Vertex_2 = self.salome_env.geompy.MakeVertexWithRef(Vertex_1, 0, 0.004, 0)
        Vertex_4 = self.salome_env.geompy.MakeVertex(0, 0.004, 0)

        Line_1 = self.salome_env.geompy.MakeLineTwoPnt(Vertex_2, Vertex_4)
        Line_4_orig = self.salome_env.geompy.MakeLineTwoPnt(Vertex_1, Vertex_2)
        Line_3 = self.salome_env.geompy.MakeLineTwoPnt(O_o, Vertex_4)
        Line_2 = self.salome_env.geompy.MakeLineTwoPnt(O_o, Vertex_1)

        Face_1 = self.salome_env.geompy.MakeFaceWires(
            [Line_4_orig, Line_1, Line_3, Line_2], 1
        )
        Vertex_5 = self.salome_env.geompy.MakeVertex(0.050, 0.07, 0)
        Vertex_6 = self.salome_env.geompy.MakeVertexWithRef(Vertex_5, 0.035, 0, 0)
        Vertex_7 = self.salome_env.geompy.MakeVertexWithRef(Vertex_6, 0, -0.035, 0)
        Vertex_8 = self.salome_env.geompy.MakeVertexWithRef(Vertex_5, 0.002, 0, 0)
        Vertex_9 = self.salome_env.geompy.MakeVertexWithRef(Vertex_7, 0, 0.002, 0)

        Arc_2 = self.salome_env.geompy.MakeArcCenter(
            Vertex_6, Vertex_8, Vertex_9, False
        )
        Arc_3 = self.salome_env.geompy.MakeArcCenter(
            Vertex_6, Vertex_5, Vertex_7, False
        )

        Line_4_v2 = self.salome_env.geompy.MakeLineTwoPnt(Vertex_5, Vertex_8)
        Arc_2_vertex_3 = self.salome_env.geompy.GetSubShape(Arc_2, [3])
        Arc_3_vertex_3 = self.salome_env.geompy.GetSubShape(Arc_3, [3])
        Line_5 = self.salome_env.geompy.MakeLineTwoPnt(
            Arc_2_vertex_3, Arc_3_vertex_3
        )

        Face_2 = self.salome_env.geompy.MakeFaceWires(
            [Arc_2, Arc_3, Line_4_v2, Line_5], 1
        )
        Revolution_1 = self.salome_env.geompy.MakeRevolution(
            Face_1, self.L4, 360 * math.pi / 180.0
        )
        Revolution_2 = self.salome_env.geompy.MakeRevolution(
            Face_2, self.L4, 360 * math.pi / 180.0
        )

        FUSE1 = self.salome_env.geompy.MakeFuseList(
            [Revolution_1, Revolution_2, REVOLUTION1_2], True
        )
        self.object = self.salome_env.geompy.MakeTranslation(
            FUSE1, self.x, self.room.H - 0.07 - self.y, self.z
        )
        if self.name is not None:
            self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()
            
        return self


class Table:
    def __init__(self, salome_env, name='Table'):

        self.salome_env = salome_env
        self.name = name
        self.faces = None

    def retangular(self, dx=0.6, dy=0.02, dz=0.6, x=1.5, y=0.6, z=1.5):
        # Criação dos vértices
        P31 = self.salome_env.geompy.MakeVertex(dx / 2, 0, dz / 2)
        P32 = self.salome_env.geompy.MakeVertexWithRef(P31, 0, dy, 0)
        P33 = self.salome_env.geompy.MakeVertexWithRef(P32, -dx, 0, 0)
        P34 = self.salome_env.geompy.MakeVertexWithRef(P33, 0, -dy, 0)

        # Definição das arestas
        L11 = self.salome_env.geompy.MakeLineTwoPnt(P31, P32)
        L12 = self.salome_env.geompy.MakeLineTwoPnt(P32, P33)
        L13 = self.salome_env.geompy.MakeLineTwoPnt(P33, P34)
        L14 = self.salome_env.geompy.MakeLineTwoPnt(P34, P31)

        # Geração da face e extrusão
        F5 = self.salome_env.geompy.MakeFaceWires([L11, L12, L13, L14], 1)
        EXTRUSION2 = self.salome_env.geompy.MakePrismVecH(F5, self.salome_env.OZ, -dz)
        
        # Translação final
        self.object = self.salome_env.geompy.MakeTranslation(EXTRUSION2, x, y, z)

        if self.name is not None:
            self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()
        
        return self

    def circular(self, raio=0.35, espessura=0.02, x=1.5, y=0.6, z=1.5):

        P1 = self.salome_env.geompy.MakeVertex(0, 0, 0)
        C1 = self.salome_env.geompy.MakeCircle(P1, self.salome_env.OY, raio)
        F1 = self.salome_env.geompy.MakeFaceWires([C1], 1)
        
        Extrusion_1 = self.salome_env.geompy.MakePrismVecH(F1, self.salome_env.OY, espessura)
        
        # Translação final
        self.object = self.salome_env.geompy.MakeTranslation(Extrusion_1, x, y, z)

        if self.name is not None:
            self.salome_env.geompy.addToStudy(self.object, self.name)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()
        
        return self
