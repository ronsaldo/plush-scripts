#!/usr/bin/python
import sys
import math
from copy import deepcopy
from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"

NSMAP = {None : SVG_NS, 'inkscape': INKSCAPE_NS, 'sodipodi' : SODIPODI_NS}

INFINITY = float('inf')

US_LETTER_WIDTH = 215.9
US_LETTER_HEIGHT = 279.4

CHILE_LEGAL_WIDTH = 216
CHILE_LEGAL_HEIGHT = 333

A4_WIDTH = 210
A4_HEIGHT = 297

PAGE_WIDTH = A4_WIDTH
PAGE_HEIGHT = A4_HEIGHT

PAGE_WIDTH = CHILE_LEGAL_WIDTH
PAGE_HEIGHT = CHILE_LEGAL_HEIGHT

PAGE_MARGIN = 5 
JOIN_MARGIN = 5

# Units
PIXELS = 1.0/3.543307

def tagName(tag, namespace):
    return '{%s}%s' % (namespace, tag)

def attribName(tag, namespace):
    return '{%s}%s' % (namespace, tag)

def extractPathPositions(path):
    components = path.replace(',', ' ').split()
    positions = []
    i = 0
    currentPosition = Vector2()
    subpathStartPosition = Vector2()
    while i < len(components):
        newAction = components[i]
        if newAction.isalpha():
            action = newAction
            i += 1

        if action in ('M', 'L'):
            currentPosition = Vector2(float(components[i]), float(components[i+1]))
            positions.append(currentPosition)
            i += 2
            if action == 'M':
                subpathStartPosition = currentPosition
            action = 'L'
        elif action in ('m', 'l'):
            currentPosition = currentPosition + Vector2(float(components[i]), float(components[i+1]))
            positions.append(currentPosition)
            i += 2
            if action == 'm':
                subpathStartPosition = currentPosition
            action = 'l'
        elif action in ('Z', 'z'):
            # This is important for relative movements.
            currentPosition = subpathStartPosition
        else:
            print components
            assert False

    return positions

# Vector2 class
class Vector2:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __add__(self, o):
        return Vector2(self.x + o.x, self.y + o.y)

    def __sub__(self, o):
        return Vector2(self.x - o.x, self.y - o.y)
    
    def __mul__(self, s):
        return Vector2(self.x*s, self.y*s)

    def __div__(self, s):
        return Vector2(self.x/s, self.y/s)

    def __neg__(self):
        return Vector2(-self.x, -self.y)

    def dot(self, o):
        return self.x*o.x + self.y*o.y

    def length2(self):
        return self.dot(self)

    def length(self):
        return math.sqrt(self.length2())

    def __repr__(self):
        return "Vector2(%f, %f)" % (self.x, self.y)

class Matrix:
    def __init__(self, values = None):
        self.values = values
        if self.values is None:
            self.values = [0]*9

    def at(self, i, j):
        return self.values[i*3 + j]

    def __mul__(self, o):
        values = []
        for i in range(3):
            for j in range(3):
                val = 0
                for k in range(3):
                    val += self.at(i, k)*o.at(k, j)
                values.append(val)
        return Matrix(values)

    @classmethod
    def translation(cls, t):
        return cls(
            [1, 0, t.x,
             0, 1, t.y,
             0, 0, 1])

    @classmethod
    def scale(cls, s):
        return cls(
            [s.x, 0, 0,
             0, s.y, 0,
             0, 0, 1])

    def __repr__(self):
        return "Matrix(%s)" % repr(self.values)

    def __str__(self):
        return str(self.values)

    def svgMatrix(self):
        return "matrix(%f,%f,%f,%f,%f,%f)" % (self.at(0,0), self.at(1,0), self.at(0,1), self.at(1,1), self.at(0,2), self.at(1,2))

class AABox2:
    def __init__(self, cmin=None, cmax=None):
        self.min = cmin
        self.max = cmax
        if self.min is None: self.min = Vector2(INFINITY, INFINITY)
        if self.max is None: self.max = Vector2(-INFINITY, -INFINITY)

    def addPoint(self, point):
        self.min.x = min(self.min.x, point.x)
        self.min.y = min(self.min.y, point.y)
        self.max.x = max(self.max.x, point.x)
        self.max.y = max(self.max.y, point.y)

    def addBox(self, box):
        self.min.x = min(self.min.x, box.min.x)
        self.min.y = min(self.min.y, box.min.y)
        self.max.x = max(self.max.x, box.max.x)
        self.max.y = max(self.max.y, box.max.y)

    def getCenter(self):
        return (self.min + self.max) * 0.5

    def getWidth(self):
        return self.max.x - self.min.x

    def getHeight(self):
        return self.max.y - self.min.y

    def getSize(self):
        return self.max - self.min

    def __repr__(self):
        return "AABox2(%s, %s)" % (repr(self.min), repr(self.max))

def boundingBoxFromPoints(points):
    box = AABox2()
    for p in points:
        box.addPoint(p)
    return box

def boundingBoxFromBoxes(boxes):
    box = AABox2()
    for b in boxes:
        box.addBox(b)
    return box

class Node:
    def __init__(self, node):
        self.node = node

    def parseChildren(self, node):
        return map(self.parseChild, node)

    def parseChild(self, node):
        tag = node.tag
        if tag == tagName('g', SVG_NS):
            return Group(node)
        if tag == tagName('path', SVG_NS):
            return Path(node)
        if tag == tagName('text', SVG_NS):
            return Group(node)
        return GenericNode(node)

    def getBoundingBox(self):
        return AABox2()

class GenericNode(Node):
    def __init__(self, node):
        Node.__init__(self, node)

class Group(Node):
    def __init__(self, node):
        Node.__init__(self, node)
        self.children = self.parseChildren(node)
        self.boundingBox = boundingBoxFromBoxes(map(lambda child: child.getBoundingBox(), self.children))

    def getBoundingBox(self):
        return self.boundingBox

class Path(Node):
    def __init__(self, node):
        Node.__init__(self, node)
        self.positions = extractPathPositions(node.attrib['d'])
        self.boundingBox = boundingBoxFromPoints(self.positions)

    def getBoundingBox(self):
        return self.boundingBox

class Text(Node):
    def __init__(self, node):
        Node.__init__(self, node)
        self.text = node.text

class Layer(Node):
    def __init__(self, node):
        Node.__init__(self, node)
        self.name = node.attrib.get(attribName('label', INKSCAPE_NS), 'layer')
        self.children = self.parseChildren(node)
        self.boundingBox = boundingBoxFromBoxes(map(lambda child: child.getBoundingBox(), self.children))

    def getBoundingBox(self):
        return self.boundingBox

    def transformScale(self, scale):
        self.transform = Matrix.scale(Vector2(scale, scale)) * Matrix.translation(-self.boundingBox.min)
        self.transformedSized = self.boundingBox.getSize() * scale

    def addMarginRectangle(self, parent, x, y, w, h):
        rect = etree.SubElement(parent, tagName('rect', SVG_NS))
        rect.attrib['width'] = '%fmm' % w
        rect.attrib['height'] = '%fmm' % h
        rect.attrib['x'] = '%fmm' % x
        rect.attrib['y'] = '%fmm' % y
        rect.attrib['style'] = 'fill: red; fill-opacity:0.3;'

    def addPageRectangle(self, parent, x, y, w, h):
        rect = etree.SubElement(parent, tagName('rect', SVG_NS))
        rect.attrib['width'] = '%fmm' % w
        rect.attrib['height'] = '%fmm' % h
        rect.attrib['x'] = '%fmm' % x
        rect.attrib['y'] = '%fmm' % y
        rect.attrib['style'] = 'fill-opacity: 0; stroke: black;'

    def addFileName(self, parent, fileName):
        text = etree.SubElement(parent, tagName('text', SVG_NS))
        text.attrib['x'] = "%fmm" % (JOIN_MARGIN*3)
        text.attrib['y'] = "%fmm" % (JOIN_MARGIN*3)
        text.attrib['style'] = "fill: gray; font-size: 20pt"
        text.text = fileName

    def exportPart(self, pageSize, i, j, outdir):
        fileName = '%s/%s_%d_%d.svg' % (outdir, self.name, i, j)
        
        viewPosition = Vector2(i*(pageSize.x - JOIN_MARGIN), j*(pageSize.y - JOIN_MARGIN))
        viewTransform = Matrix.translation(-viewPosition/PIXELS)

        newLayer = deepcopy(self.node)
        newLayer.attrib['transform'] = (viewTransform*self.transform).svgMatrix()

        newRoot = etree.Element(tagName('svg', SVG_NS), nsmap=NSMAP)
        newRoot.attrib['version'] = '1.1'
        newRoot.attrib['width'] = '%fmm' % pageSize.x
        newRoot.attrib['height'] = '%fmm' % pageSize.y

        newRoot.append(newLayer)

        # Add margin
        #self.addMarginRectangle(newRoot, 0, 0, pageSize.x, JOIN_MARGIN)
        #self.addMarginRectangle(newRoot, 0, 0, JOIN_MARGIN, pageSize.y)

        self.addMarginRectangle(newRoot, 0, pageSize.y - JOIN_MARGIN, pageSize.x, JOIN_MARGIN)
        self.addMarginRectangle(newRoot, pageSize.x - JOIN_MARGIN, 0, JOIN_MARGIN, pageSize.y)

        # Add rectangle
        self.addPageRectangle(newRoot, 0, 0, pageSize.x, pageSize.y)

        # Add the file name
        self.addFileName(newRoot, fileName)

        with open(fileName, 'w') as f:
            text = etree.tostring(newRoot, encoding="UTF-8", xml_declaration = True, pretty_print=True)
            f.write(text)

    def export(self, outdir):
        size = self.transformedSized * PIXELS

        margin = PAGE_MARGIN*2
        joinMargin = JOIN_MARGIN
        if size.x > size.y:
            # Landscape
            pageSize = Vector2(PAGE_HEIGHT - margin, PAGE_WIDTH - margin)
        else:
            # Portrait
            pageSize = Vector2(PAGE_WIDTH - margin, PAGE_HEIGHT - margin)
        columns = int(math.ceil(size.x / (pageSize.x - joinMargin)))
        rows = int(math.ceil(size.y / (pageSize.y - joinMargin)))
        for i in range(columns):
            for j in range(rows):
                self.exportPart(pageSize, i, j, outdir)
    
class Document(Node):
    def __init__(self, document):
        Node.__init__(self, document.getroot())
        self.layers = []
        self.layerDict = {}
        self.units = PIXELS
        self.scale = 1.0
        for child in self.node:
            tag = child.tag
            if tag == tagName('g', SVG_NS):
                layer = Layer(child)
                self.layers.append(layer)
                self.layerDict[layer.name] = layer

    def scaleLayerWidth(self, layerName, targetWidth):
        layer = self.layerDict.get(layerName)
        bbox = layer.getBoundingBox()
        layerWidth = bbox.getWidth()
        self.scale = targetWidth / (layerWidth * PIXELS)

    def scaleLayerHeight(self, layerName, targetHeight):
        layer = self.layerDict.get(layerName)
        bbox = layer.getBoundingBox()
        layerHeight = bbox.getHeight()
        self.scale = targetHeight / (layerHeight * PIXELS)

    def transformLayers(self):
        print 'Computed scale factor', self.scale
        for layer in self.layers:
            layer.transformScale(self.scale)

    def exportLayers(self, outDir):
        for layer in self.layers:
            layer.export(outDir)

# Parse the command
class Program:
    def __init__(self):
        self.inputFileName = None
        self.scaleLayer = None
        self.scaleLayerWidth = None
        self.scaleLayerHeight = None
        self.outDir = '.'

    def parseCommandLine(self):
        i = 1
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == '-out':
                i += 1
                self.outDir = sys.argv[i]
            elif arg == '-scale-layer':
                i += 1
                self.scaleLayer = sys.argv[i]

            elif arg == '-scale-width':
                i += 1
                self.scaleLayerWidth = float(sys.argv[i])
            elif arg == '-scale-height':
                i += 1
                self.scaleLayerHeight = float(sys.argv[i])
            else:
                self.inputFileName = arg

            i += 1

    def printHelp(self):
        print 'Missing input files'

    def run(self):
        # Parse the command line
        self.parseCommandLine()
        if self.inputFileName is None:
            self.printHelp() 

        with open(self.inputFileName, 'r') as f:
            document = Document(etree.parse(f))

        # Compute the layer scale.
        if self.scaleLayer is not None and self.scaleLayerWidth is not None:
            document.scaleLayerWidth(self.scaleLayer, self.scaleLayerWidth)
        if self.scaleLayer is not None and self.scaleLayerHeight is not None:
            document.scaleLayerHeight(self.scaleLayer, self.scaleLayerHeight)

        # Transform the layers
        document.transformLayers()

        # Export the layers
        document.exportLayers(self.outDir)

Program().run()

