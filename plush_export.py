import bpy
import xml.etree.ElementTree as ET
from mathutils import *
from math import *

EPSILON = 0.0000001
def closeTo(a, b):
    d = a -b
    return -EPSILON <= d and d <= EPSILON

def polygonWindingNumber(positions):
    number = 0
    N = len(positions)
    for i in range(N):
        p1 = positions[i]
        p2 = positions[(i+1) % N]
        p3 = positions[(i+2) % N]
        u = p2 - p1
        v = p3 - p1
        number +=  u.cross(v)
    return number

def colorToHex(color):
    r = round(color.r*255)
    g = round(color.g*255)
    b = round(color.b*255)
    return "#%02X%02X%02X" % (r,g,b)

def pointPolygonWindingNumber(point, positions):
    number = 0
    N = len(positions)
    for i in range(N):
        p1 = positions[i]
        p2 = positions[(i+1)% N]
        u = p1 - point
        v = p2 - point
        number +=  u.cross(v)
    return number

def pointInsidePolygon(point, polygon):
    return not closeTo(pointPolygonWindingNumber(point, polygon), 0.0)

class Outline:
    def __init__(self, root):
        self.root = root
        self.innerTriangle = None
        self.innerVertex = None
        self.color = Color((1.0, 1.0, 1.0))
        
    def extractVertices(self):
        self.vertices = []
        self.edges = []
        current = self.root
        self.edges.append(current)
        self.vertices.append(current.v1)
        
        current = current.next
        while current != self.root:
            self.edges.append(current)
            self.vertices.append(current.v1)
            current = current.next
            
        # Set the outline flag
        for vertex in self.vertices:
            vertex.isOutline = True
        
        self.positions = list(map(lambda x: x.position, self.vertices))
        
        # Compute the centroid
        self.centroid = self.positions[0].copy()
        for i in range(len(self.positions)):
            self.centroid += self.positions[i]
        self.centroid /= len(self.positions)
        
        # Compute the bounding box
        self.max = self.positions[0].copy()
        self.min = self.positions[0].copy()
        for position in self.positions:
            self.max[0] = max(self.max[0], position[0])
            self.max[1] = max(self.max[1], position[1])
            self.min[0] = min(self.min[0], position[0])
            self.min[1] = min(self.min[1], position[1])
        self.center = (self.max + self.min)*0.5
        
        winding = polygonWindingNumber(self.positions)
        if winding < 0:
            self.positions.reverse()

    def findInnerTriangle(self, allTriangles):
        for edge in self.edges:
            for triangle in edge.triangles:
                for vertex in triangle.getVertices():
                    if vertex.isOutline: continue
                    if vertex == edge.v1: continue
                    if vertex == edge.v2: continue
                    if pointInsidePolygon(vertex.position, self.positions):
                        self.innerTriangle = triangle
                        self.innerVertex = vertex
                        return
    
    def makePathData(self, width, height):
        result = "M %s" % (self.vectorToString(self.vertices[0].position, width, height))
        for i in range(1, len(self.vertices)):
            result += " L %s" % (self.vectorToString(self.vertices[i].position, width, height))
        result += " Z"
        return result
        
    def vectorToString(self, vector, width, height):
        return "%f %f" % (vector[0]*width, (1.0 - vector[1])*height)

    def centerFor(self, width, height):
        return (self.center[0]*width, (1.0 - self.center[1])*height)
    
    def centroidFor(self, width, height):
        return (self.centroid[0]*width, (1.0 - self.centroid[1])*height)
        
    def extractMetadata(self):
        face = self.innerTriangle
        if face is not None:
            object = face.object
            mesh = object.data
            blenderFace = face.face
            # Use the material for setting the fill color.
            if len(mesh.materials) > 0:
                material = mesh.materials[blenderFace.material_index]
                self.color = material.diffuse_color
                
            if self.innerVertex is not None:
                blenderVertex = mesh.vertices[self.innerVertex.blenderIndex]
                vgroups = blenderVertex.groups
                if len(vgroups) > 0:
                    vgroup = object.vertex_groups[vgroups[0].group]
                    self.name = vgroup.name

class Vertex:
    def __init__(self, blenderIndex, index, position):
        self.blenderIndex = blenderIndex
        self.index = index
        self.position = position
        self.isOutline = False

class Edge:
    def __init__(self, v1, v2):
        self.v1 = v1
        self.v2 = v2
        self.triangles = []
        self.connections = []
        self.prev = None
        self.next = None
        self.visited = False
        
    def isOutline(self):
        return len(self.triangles) < 2
        
    def addTriangle(self, newTriangle):
        assert len(self.triangles) < 2
        self.triangles.append(newTriangle)
        
class Triangle:
    def __init__(self, object, face, v1, v2, v3, e1, e2, e3):
        self.object = object
        self.face = face
        self.v1 = v1
        self.v2 = v2
        self.v3 = v3
        self.e1 = e1
        self.e2 = e2
        self.e3 = e3
         
    def getVertices(self):
        return (self.v1, self.v2, self.v3)
    
class Exporter:
    def __init__(self):
        self.outlines = []
        self.vertices = {}
        self.edges = {}
        self.triangles = []
        self.outline_edges = {}
        self.width = 1024
        self.height = 1024
        
    def getVertex(self, vec, index):
        coordinates = (vec.x, vec.y)
        vertex = self.vertices.get(coordinates, None)
        if vertex != None: return vertex
        
        vertex = Vertex(index, len(self.vertices), vec)
        self.vertices[coordinates] = vertex
        return vertex
        
    def addEdge(self, p1, p2):
        assert p1 != p2
        i1 = min(p1.index, p2.index)
        i2 = max(p1.index, p2.index)
        assert i1 != i2
        if (i1, i2) in self.edges:
            return self.edges[(i1, i2)]
        
        edge = Edge(p1, p2)
        self.edges[(i1,i2)] = edge
        return edge
        
    def addTriangle(self, object, face, p1, p2, p3):
        e1 = self.addEdge(p1, p2)
        e2 = self.addEdge(p2, p3)
        e3 = self.addEdge(p3, p1)
        t = Triangle(object, face, p1, p2, p3, e1, e2, e3)
        e1.addTriangle(t)
        e2.addTriangle(t)
        e3.addTriangle(t)
        self.triangles.append(t)
        
    def addObject(self, object):
        # Only support mesh objects
        if object.type != 'MESH':
            return
        mesh = object.data
        mesh.update(calc_tessface=True)
        faces = mesh.tessfaces
        uvmap_layer = mesh.tessface_uv_textures.active
        uv_faces = uvmap_layer.data
        
        for face in faces:
            uvface = uv_faces[face.index]
            if len(face.vertices) == 3:
                p1 = self.getVertex(uvface.uv1, face.vertices[0])
                p2 = self.getVertex(uvface.uv2, face.vertices[1])
                p3 = self.getVertex(uvface.uv3, face.vertices[2])
                self.addTriangle(object, face, p1, p2, p3)
            else:
                p1 = self.getVertex(uvface.uv1, face.vertices[0])
                p2 = self.getVertex(uvface.uv2, face.vertices[1])
                p3 = self.getVertex(uvface.uv3, face.vertices[2])
                p4 = self.getVertex(uvface.uv4, face.vertices[3])
                self.addTriangle(object, face, p1, p2, p3)
                self.addTriangle(object, face, p3, p4, p1)
                
    def extractOutlines(self):
        self.outline_edge_list = []
        for edge in self.edges.values():
            if edge.isOutline():
                self.outline_edge_list.append(edge)
                p1Edges = self.outline_edges.get(edge.v1, [])
                p2Edges = self.outline_edges.get(edge.v2, [])
                
                assert len(p1Edges) < 2
                assert len(p2Edges) < 2
                for newEdge in p1Edges:
                    edge.connections.append(newEdge)
                    newEdge.connections.append(edge)
                    
                for newEdge in p2Edges:
                    edge.connections.append(newEdge)
                    newEdge.connections.append(edge)
                
                p1Edges.append(edge)
                p2Edges.append(edge)
                self.outline_edges[edge.v1] = p1Edges
                self.outline_edges[edge.v2] = p2Edges

    def fixOutlineOrder(self, edge):
        if edge.visited: return
        
        outline = Outline(edge)
        self.outlines.append(outline)
        prev = None
        current = edge
        count = 1
        first = True
        while first or current != edge:
            current.visited = True
            first = False
            assert len(current.connections) <= 2
            next = None
            for node in current.connections:
                if node != prev:
                    next = node
                    
            # Set current and next links
            current.next = next
            next.prev = current
            
            # Advance
            prev = current
            current = next
            count += 1
            
    def fixOutlineOrders(self):
        for edge in self.outline_edge_list:
            self.fixOutlineOrder(edge)
            
    def buildOutlines(self):
        self.extractOutlines()
        self.fixOutlineOrders()
        for i in range(len(self.outlines)):
            outline = self.outlines[i]
            outline.name = 'Outline%03d' % i
            outline.extractVertices()
            outline.findInnerTriangle(self.triangles)
            outline.extractMetadata()
        self.outlines.sort(key=lambda x: x.name)
    
    def exportOutlineName(self, outline, layer, group):
        x, y = outline.centerFor(self.width, self.height)
        text = ET.SubElement(group, 'text')
        text.attrib['fill'] = 'black'
        text.attrib['x'] = str(x)
        text.attrib['y'] = str(y)
        text.text = outline.name
    
    def exportOutline(self, outline, parent):
        layer = ET.SubElement(parent, 'g')
        layer.attrib['inkscape:groupmode'] = 'layer'
        layer.attrib['inkscape:label'] = outline.name
        group = ET.SubElement(layer, 'g')
        
        path = ET.SubElement(group, 'path')
        path.attrib['d'] = outline.makePathData(self.width, self.height)
        path.attrib['stroke'] = 'black'
        path.attrib['fill'] = colorToHex(outline.color)
        
        self.exportOutlineName(outline, layer, group)
            
    def buildXml(self):
        svg_uri="http://www.w3.org/2000/svg"
        sodipodi_uri = 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
        inkscape_uri = 'http://www.inkscape.org/namespaces/inkscape'
        ET.register_namespace('svg', svg_uri)
        ET.register_namespace('sodipodi', sodipodi_uri)
        ET.register_namespace('inkscape', inkscape_uri)
        self.outlineIndex = 0
        
        document = ET.Element('svg')
        document.attrib['xmlns:svg'] = svg_uri
        document.attrib['xmlns'] = svg_uri
        document.attrib['xmlns:sodipodi'] = sodipodi_uri
        document.attrib['xmlns:inkscape'] = inkscape_uri
        document.attrib['width'] = str(self.width)
        document.attrib['height'] = str(self.height)
        document.attrib['version'] = '1.1'
        
        
        for outline in self.outlines:
            self.exportOutline(outline, document)
        return document
    
    def export(self, filepath):
        self.buildOutlines()
        document = self.buildXml()
        with open(filepath, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n')
            f.write(ET.tostring(document, encoding="UTF-8"))
            
def write_some_data(context, filepath, selected):
    exporter = Exporter()
    if selected:
        for obj in context.selected_objects:
            exporter.addObject(obj)
    else:
        for obj in bpy.data.objects:
            exporter.addObject(obj)
    exporter.export(filepath)
    return {'FINISHED'}


# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class ExportSomeData(Operator, ExportHelper):
    """Plush toy SVG blueprint"""
    bl_idname = "plushtoy.svg_blueprint"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Plush Toy SVG blueprint"

    # ExportHelper mixin class uses this
    filename_ext = ".svg"

    filter_glob = StringProperty(
            default="*.svg",
            options={'HIDDEN'},
            )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    selected = BoolProperty(
            name="Export Selected",
            description="Exports selected objects",
            default=True,
            )

    def execute(self, context):
        return write_some_data(context, self.filepath, self.selected)


# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(ExportSomeData.bl_idname, text="Plush SVG Blueprint")


def register():
    bpy.utils.register_class(ExportSomeData)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ExportSomeData)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
