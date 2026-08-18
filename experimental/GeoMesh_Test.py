"""Test sandbox for extending GeoMesh with Window and ACUnit.

This module keeps the original GeoMesh implementation untouched and provides
an isolated place to evaluate the geometry changes needed for:

- Window: a 2D rectangular opening on a wall.
- ACUnit: a wall-attached solid with a distinct inlet face group.

Design notes:
- Window objects must be inserted through partitioning, not the normal cut
  path used for solid volumes.
- ACUnit body groups can reuse the existing wall-like mesh treatment so the
  base Mesh class remains usable.
- Simulation and Manager still need explicit class registration if these new
  objects are to be recorded into machine scripts.
"""
import math
import inspect
import sys
import time

import GEOM
import SALOMEDS
import SMESH
import salome
import salome_notebook
from salome.geom import geomBuilder
from salome.smesh import smeshBuilder
import pandas as pd
import os
import math

import GeoMesh as base


salome_start = base.salome_start
salome_update = base.salome_update

Salome_Env = base.Salome_Env
Object = base.Object
Mesh = base.Mesh
Person_seated = base.Person_seated
Person_standing = base.Person_standing
Dip_type_00 = base.Dip_type_00
Dip_type_01 = base.Dip_type_01
Dip_type_02 = base.Dip_type_02
Dip_type_03 = base.Dip_type_03
Table_retangular = base.Table_retangular
Table_circular = base.Table_circular


def _is_close_center(geompy, face, target_coords, tolerance):
    center = geompy.MakeCDG(face)
    coords = geompy.PointCoordinates(center)
    return all(abs(coords[i] - target_coords[i]) < tolerance for i in range(3))


def _make_rectangle_face(geompy, wall, center_x, center_y, center_z, width, height):
    half_width = width / 2.0
    half_height = height / 2.0

    if wall in ("x0", "x1"):
        p1 = geompy.MakeVertex(center_x, center_y - half_width, center_z - half_height)
        p2 = geompy.MakeVertex(center_x, center_y + half_width, center_z - half_height)
        p3 = geompy.MakeVertex(center_x, center_y + half_width, center_z + half_height)
        p4 = geompy.MakeVertex(center_x, center_y - half_width, center_z + half_height)
    elif wall in ("y0", "y1"):
        p1 = geompy.MakeVertex(center_x - half_width, center_y, center_z - half_height)
        p2 = geompy.MakeVertex(center_x + half_width, center_y, center_z - half_height)
        p3 = geompy.MakeVertex(center_x + half_width, center_y, center_z + half_height)
        p4 = geompy.MakeVertex(center_x - half_width, center_y, center_z + half_height)
    else:
        raise ValueError("wall must be one of: x0, x1, y0, y1")

    l1 = geompy.MakeLineTwoPnt(p1, p2)
    l2 = geompy.MakeLineTwoPnt(p2, p3)
    l3 = geompy.MakeLineTwoPnt(p3, p4)
    l4 = geompy.MakeLineTwoPnt(p4, p1)
    return geompy.MakeFaceWires([l1, l2, l3, l4], 1)


class Window(Object):
    """2D rectangular opening that must be partitioned into a wall face."""

    def __init__(
        self,
        salome_env=None,
        wall="x0",
        width=0.8,
        height=0.6,
        x=0.0,
        y=1.5,
        z=1.5,
        **kwargs,
    ):
        super().__init__(salome_env, **kwargs)
        self.wall = wall
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.z = z
        self.object = _make_rectangle_face(
            self.salome_env.geompy, wall, x, y, z, width, height
        )
        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()


class ACUnit(Object):
    """Wall-attached unit with a separate inlet face reference."""

    def __init__(
        self,
        salome_env=None,
        wall="x0",
        x=0.0,
        y=1.5,
        z=1.5,
        body_width=0.75,
        body_height=0.32,
        body_depth=0.22,
        inlet_width=0.24,
        inlet_height=0.10,
        inlet_depth=0.04,
        **kwargs,
    ):
        super().__init__(salome_env, **kwargs)
        self.wall = wall
        self.x = x
        self.y = y
        self.z = z
        self.body_width = body_width
        self.body_height = body_height
        self.body_depth = body_depth
        self.inlet_width = inlet_width
        self.inlet_height = inlet_height
        self.inlet_depth = inlet_depth

        geompy = self.salome_env.geompy

        if wall == "x0":
            normal = geompy.MakeVectorDXDYDZ(1, 0, 0)
            body_face = _make_rectangle_face(geompy, wall, x, y, z, body_width, body_height)
            inlet_center_x = x + body_depth
            inlet_face = _make_rectangle_face(
                geompy, wall, inlet_center_x, y, z, inlet_width, inlet_height
            )
        elif wall == "x1":
            normal = geompy.MakeVectorDXDYDZ(-1, 0, 0)
            body_face = _make_rectangle_face(geompy, wall, x, y, z, body_width, body_height)
            inlet_center_x = x - body_depth
            inlet_face = _make_rectangle_face(
                geompy, wall, inlet_center_x, y, z, inlet_width, inlet_height
            )
        elif wall == "y0":
            normal = geompy.MakeVectorDXDYDZ(0, 1, 0)
            body_face = _make_rectangle_face(geompy, wall, x, y, z, body_width, body_height)
            inlet_center_y = y + body_depth
            inlet_face = _make_rectangle_face(
                geompy, wall, x, inlet_center_y, z, inlet_width, inlet_height
            )
        elif wall == "y1":
            normal = geompy.MakeVectorDXDYDZ(0, -1, 0)
            body_face = _make_rectangle_face(geompy, wall, x, y, z, body_width, body_height)
            inlet_center_y = y - body_depth
            inlet_face = _make_rectangle_face(
                geompy, wall, x, inlet_center_y, z, inlet_width, inlet_height
            )
        else:
            raise ValueError("wall must be one of: x0, x1, y0, y1")

        self.inlet_center = (x, y, z)
        self.inlet_face = inlet_face

        body_solid = geompy.MakePrismVecH(body_face, normal, body_depth)
        inlet_solid = geompy.MakePrismVecH(inlet_face, normal, inlet_depth)
        self.object = geompy.MakeFuseList([body_solid, inlet_solid], True, True)

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()


class Room(base.Room):
    """Room variant that can host wall windows and AC units."""

    def __init__(self, salome_env=None, dx=3.000, dy=3.000, dz=3.000, **kwargs):
        super().__init__(salome_env=salome_env, dx=dx, dy=dy, dz=dz, **kwargs)
        self.window_faces = []
        self.ac_inlet_faces = []
        self.ac_body_faces = []

    def add(self, obj_list):
        for obj in obj_list:
            if not getattr(obj, "name", None):
                raise ValueError("Object name is required. Pass name=... when creating objects.")

        self.obj_list = self.obj_list + obj_list

        window_objects = [obj.object for obj in obj_list if isinstance(obj, Window)]
        solid_objects = [obj.object for obj in obj_list if not isinstance(obj, Window)]

        for window_face in window_objects:
            self.object = self.salome_env.geompy.MakePartitionNonSelfIntersectedShape(
                [self.object], [window_face], [], [],
                self.salome_env.geompy.ShapeType["SOLID"], 0, [], 1, True
            )

        if solid_objects:
            self.object = self.salome_env.geompy.MakeCutList(
                self.object, solid_objects, True
            )

        self.n += 1
        self.salome_env.geompy.addToStudy(self.object, self.name + str(self.n))

        if salome.sg.hasDesktop():
            salome.sg.updateObjBrowser()

        self.create_faces_groups()

    def create_faces_groups(self, group_list=None, group_name=None):
        faces_room = self.salome_env.geompy.ExtractShapes(
            self.object, self.salome_env.geompy.ShapeType["FACE"], True
        )

        tolerance = 1e-6
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

            group_faces = self.salome_env.geompy.CreateGroup(
                self.object, self.salome_env.geompy.ShapeType["FACE"]
            )
            self.faces_groups.append(group_faces)

            if isinstance(obj, (Dip_type_00, Dip_type_01, Dip_type_02, Dip_type_03)):
                self.faces_names_groups.append(("dip", obj.name))
            elif isinstance(obj, (Table_retangular, Table_circular)):
                self.faces_names_groups.append(("table", obj.name))
            elif isinstance(obj, (Person_seated, Person_standing)):
                self.faces_names_groups.append(("person", obj.name))
            elif isinstance(obj, Window):
                self.faces_names_groups.append(("wall", f"wall_window_{obj.name}"))
            elif isinstance(obj, ACUnit):
                self.faces_names_groups.append(("wall", f"wall_ac_{obj.name}"))
            else:
                self.faces_names_groups.append(("wall", obj.name))

            dip_y_max = 0
            dip_face_max = None
            ac_inlet_face_max = None
            ac_inlet_area = None

            for face_obj in faces_obj:
                for face_room in faces_room:
                    if isinstance(obj, (Dip_type_00, Dip_type_01, Dip_type_02, Dip_type_03)):
                        center = self.salome_env.geompy.MakeCDG(face_room)
                        coords = self.salome_env.geompy.PointCoordinates(center)

                        cond_x = abs(coords[0] - obj.x) < tolerance
                        cond_z = abs(coords[2] - obj.z) < tolerance

                        if cond_x and cond_z and coords[1] > dip_y_max:
                            dip_y_max = coords[1]
                            dip_face_max = face_room

                    if isinstance(obj, ACUnit):
                        center = self.salome_env.geompy.MakeCDG(face_room)
                        coords = self.salome_env.geompy.PointCoordinates(center)
                        target = obj.inlet_center
                        if all(abs(coords[i] - target[i]) < tolerance for i in range(3)):
                            properties = self.salome_env.geompy.BasicProperties(face_room)
                            if len(properties) >= 2:
                                area = properties[1]
                                if ac_inlet_area is None or area < ac_inlet_area:
                                    ac_inlet_area = area
                                    ac_inlet_face_max = face_room

                    distance = self.salome_env.geompy.MinDistance(face_obj, face_room)
                    if distance < tolerance:
                        properties = self.salome_env.geompy.BasicProperties(face_room)
                        if len(properties) >= 2:
                            area = properties[1]
                            if area < self.area:
                                face_id = self.salome_env.geompy.GetSubShapeID(
                                    self.object, face_room
                                )
                                self.salome_env.geompy.AddObject(group_faces, face_id)
                                face_ids.append(face_id)
                                face_wall_ids = list(set(face_wall_ids) - {face_id})

            if isinstance(obj, (Dip_type_00, Dip_type_01, Dip_type_02, Dip_type_03)):
                face_inlet_id = self.salome_env.geompy.GetSubShapeID(
                    self.object, dip_face_max
                )
                group_inlet = self.salome_env.geompy.CreateGroup(
                    self.object, self.salome_env.geompy.ShapeType["FACE"]
                )

                self.faces_groups.append(group_inlet)
                self.faces_names_groups.append(("inlet", "inlet_" + obj.name))

                self.salome_env.geompy.AddObject(group_inlet, face_inlet_id)
                self.salome_env.geompy.addToStudyInFather(
                    self.object, group_inlet, "inlet_" + obj.name
                )
                self.inlet_faces.append(face_inlet_id)

                face_wall_ids = list(set(face_wall_ids) - {face_inlet_id})
                face_ids = list(set(face_ids) - {face_inlet_id})
                self.salome_env.geompy.RemoveObject(group_faces, face_inlet_id)

            if isinstance(obj, ACUnit) and ac_inlet_face_max is not None:
                face_inlet_id = self.salome_env.geompy.GetSubShapeID(
                    self.object, ac_inlet_face_max
                )
                group_inlet = self.salome_env.geompy.CreateGroup(
                    self.object, self.salome_env.geompy.ShapeType["FACE"]
                )

                self.faces_groups.append(group_inlet)
                self.faces_names_groups.append(("inlet", "inlet_" + obj.name))

                self.salome_env.geompy.AddObject(group_inlet, face_inlet_id)
                self.salome_env.geompy.addToStudyInFather(
                    self.object, group_inlet, "inlet_" + obj.name
                )
                self.ac_inlet_faces.append(face_inlet_id)

                face_wall_ids = list(set(face_wall_ids) - {face_inlet_id})
                face_ids = list(set(face_ids) - {face_inlet_id})
                self.salome_env.geompy.RemoveObject(group_faces, face_inlet_id)

            face_ids.sort()
            self.salome_env.geompy.addToStudyInFather(
                self.object, group_faces, "obj_" + obj.name
            )
            obj.faces = face_ids

            if isinstance(obj, Window):
                self.window_faces.extend(face_ids)
            elif isinstance(obj, ACUnit):
                self.ac_body_faces.extend(face_ids)

        face_ids = []

        group_outlet = self.salome_env.geompy.CreateGroup(
            self.object, self.salome_env.geompy.ShapeType["FACE"]
        )
        self.faces_groups.append(group_outlet)
        self.faces_names_groups.append(("outlet", "outlet"))

        for face_room in faces_room:
            center = self.salome_env.geompy.MakeCDG(face_room)
            coords = self.salome_env.geompy.PointCoordinates(center)
            properties = self.salome_env.geompy.BasicProperties(face_room)

            is_top_bottom = (
                abs(coords[1] - self.H) < tolerance or abs(coords[1]) < tolerance
            )

            if is_top_bottom and properties[1] < self.area:
                face_id = self.salome_env.geompy.GetSubShapeID(
                    self.object, face_room
                )
                if face_id not in self.inlet_faces and face_id not in self.ac_inlet_faces:
                    self.salome_env.geompy.AddObject(group_outlet, face_id)
                    face_ids.append(face_id)

        self.salome_env.geompy.addToStudyInFather(
            self.object, group_outlet, "outlet"
        )
        self.outlet_faces = face_ids
        face_wall_ids = list(set(face_wall_ids) - set(face_ids))
        face_wall_ids.sort()
        self.wall_faces = face_wall_ids

        group_wall = self.salome_env.geompy.CreateGroup(
            self.object, self.salome_env.geompy.ShapeType["FACE"]
        )

        self.faces_groups.append(group_wall)
        self.faces_names_groups.append(("wall", "wall"))

        for face_id in face_wall_ids:
            self.salome_env.geompy.AddObject(group_wall, face_id)

        self.salome_env.geompy.addToStudyInFather(
            self.object, group_wall, "wall"
        )

        salome_update()
